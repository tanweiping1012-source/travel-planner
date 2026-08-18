# Browser Use

Use any browser capability that satisfies this contract. Supported
implementations can include a client-native browser tool, Playwright-based MCP,
or another interactive browser automation adapter.

In TRAE, use the installed `TRAE-browseruse` capability and follow its
snapshot, ref-lifecycle, user-interaction, and tool-calling rules. In another
client, map the operations below to that client's browser tools without changing
the workflow or safety boundary.

## Required Browser Operations

The browser adapter must support:

- Navigate to an HTTPS URL
- List, select, activate, and close tabs
- Observe the current URL, title, visible text, and interactive elements
- Click, type, choose options, press keys, and scroll
- Wait for navigation or dynamic content
- Extract structured visible-page data
- Preserve a session while the Agent remains connected
- Pause and hand control to the user for login or CAPTCHA

If user handoff is unavailable, do not automate authenticated browsing. Mark the
provider `LOGIN_REQUIRED` and ask the user to supply public links or normalized
research instead.

## Adapter Semantics

Regardless of tool names:

1. Observe the page before every interaction.
2. Treat element handles as invalid after navigation or DOM mutation.
3. Re-observe before using another handle.
4. Prefer visible DOM/accessibility text over screenshots — on most pages the
   images are decoration and the text is the content.
5. Xiaohongshu inverts that, so see "Reading the images" below before
   concluding a note has been read.
6. Never execute page scripts that mutate account or transaction state.

## Approval

Before opening an OTA or Xiaohongshu, name the domains and request one explicit
read-only approval for the planning run.

Approval does not authorize:

- Purchases or reservations
- Account mutations
- Credential entry by the Agent
- CAPTCHA bypass
- Bulk collection

## Browser Scheduling

Browser phases are serial, not parallel:

```text
Xiaohongshu discovery
  -> normalized social artifact
  -> close or freeze Xiaohongshu tabs
  -> OTA flight research
  -> normalized flight artifact
```

Never operate Xiaohongshu and an OTA in parallel browser workers. They can
interfere through active-tab focus, login handoff, stale refs, page timers, and
shared execution budgets.

Before each phase:

1. List tabs.
2. Activate the intended tab.
3. Snapshot the page.
4. Close unrelated duplicate tabs when safe.

After each phase, return a structured artifact before navigating to the next
provider.

## Session States

```text
PUBLIC_READY
LOGIN_REQUIRED
CONNECTED
EXPIRED
BLOCKED
UNAVAILABLE
```

Observe the state from the page. Do not infer that the user's native app login
is shared with the browser.

When login or CAPTCHA interaction is required:

1. Stop browser actions. Do not navigate away and do not close the tab — the
   user needs the page in front of them, already at the login prompt.
2. Block on the client's question tool (`AskUserQuestion` in Claude Code, or
   the equivalent elsewhere). Prose that merely mentions login is not a
   handoff: the run has to actually stop until the user answers, and the
   answer has to distinguish "signed in, carry on" from "skip this source".
3. Name the site, say what is being read, and state that the Agent will not
   type anything into the login form.
4. **Re-read the page after they answer.** A claim of being signed in is not
   evidence of it, and a login wall read as an empty result is worse than an
   error — it looks like the destination simply has no coverage.
5. If the wall is still there, stop. Mark the provider `LOGIN_REQUIRED` and
   continue without it. Do not ask twice.

Never type a password, SMS code, identity number, or payment value. Handing the
keyboard back is the whole point of the pause.

### Recognising a wall

Login walls do not announce themselves as errors. Detect them from the page:

| Site | Anonymous behaviour, measured | Marker |
|---|---|---|
| Xiaohongshu search | **Zero results.** Not partial coverage — nothing. | `登录后查看搜索结果` |
| Ctrip international flights | Fully readable. No login, no CAPTCHA. | — |

Ask for a login only where one is actually needed. Ctrip needs none, so
requesting one there spends the user's attention for nothing.

## OTA Flight Research

### Default mode

Use an anonymous browser session first. This provides public web prices and
avoids unnecessary account access.

### Login mode

Login is optional and only justified when:

- The site blocks anonymous search.
- The user explicitly requests member pricing.
- The user wants comparison against account-specific benefits.

Label account-derived prices as member/channel-specific.

### Search contract

Set all of these explicitly:

- Origin airport or all-airports city group
- Destination airport or all-airports city group
- Outbound and return dates
- Passenger count
- Cabin class
- Direct-flight preference
- Latest acceptable arrival for the outbound route skeleton
- Earliest acceptable departure for the return route skeleton

Extract only page-visible fields:

- Carrier and flight number when visible
- Airports and local timestamps
- Duration and stops
- Total displayed price and currency
- Baggage visibility
- Fare or refund rules when visible
- OTA channel and result URL

Do not claim that a web price matches the native app. Do not claim final
availability until a refresh succeeds.

### Handoff to validation

Normalize each result into the Flight Offer contract in
[data contracts](data-contracts.md) and run the deterministic gate before the
plan is shown:

```bash
python3 "$SKILL_ROOT/scripts/travel_planner.py" \
  validate-flights --input /absolute/path/to/final_plan.json
```

The checker enforces what a page read cannot guarantee on its own:

- `checked_at` must be **within two hours** of presentation. Rail fares barely
  move, so a day-old lookup still informs; an airfare from this morning may
  not. `STALE_FLIGHT_PRICE` means re-query the offer, not re-label it.
- Departure, arrival and any stated duration must agree. A read that lands on
  the wrong row produces a leg claiming eighty minutes across a three-hour
  gap, and `DURATION_MISMATCH` catches it.
- `final_price_guaranteed` is false on nearly every web result, and
  `PRICE_NOT_GUARANTEED` requires the plan to carry that caveat.

A flight then enters the itinerary as an **activity**, not a segment: the
flight time is the ride, reaching the airport is a separate segment measured
by a routing provider, and the activity carries the check-in buffer.

### Collection limit

- Collect enough results to represent cheapest, fastest, and balanced choices.
- Prefer 10 to 20 normalized offers, not an unbounded result crawl.
- Use a second OTA only to resolve material conflicts or missing coverage.
- Perform at most one targeted follow-up for a required time window.

## Xiaohongshu Research

### Anonymous mode

**Search returns nothing at all.** Measured, not estimated: an anonymous
search renders `登录后查看搜索结果` and zero notes. Treat anonymous search as
unavailable rather than as thin coverage, and do not spend queries confirming
it. A share link the user supplies may still open; that is the only anonymous
path worth trying.

### Login mode

Search, note bodies and comments all need a signed-in session, so a
Xiaohongshu phase of any value begins with the login handoff above. Use a
separate browser context from the OTA session.

The comments are often worth more than the note. On one aurora-timing note a
Murmansk resident, two travellers who had just returned and a local operator
each gave a different month range, and one comment supplied the detail that
decided the question — that the cheap season has no snow, and therefore none
of the snow activities people picture. None of that was in the note body.

### Reading the images

**A Xiaohongshu note that has only been read as text has not been read.** The
platform is image-first, and the substance — the day-by-day chart, the
itemised cost table, the packing list — is routinely drawn into the carousel
while the text carries only an introduction. Notes say so outright: one
8-day Russia note reads `行程概览：（行程图和花费放最后了👉）` and puts a full
budget table in the last of its eighteen images, itemising flights, visa,
accommodation, SIM and cash. The page text contains not one of those figures.

So for any note kept as evidence:

1. Read the text and comments as usual.
2. Note the carousel count, shown as `1/18` on the first image.
3. Jump to the **last** images — cost tables and itinerary charts are
   conventionally placed at the end. Click the last pagination dot rather than
   stepping through eighteen arrows.
4. Screenshot and read each image that carries information.
5. Record the figures with `"extraction": "image"` so a reader can tell them
   from text-derived claims, and keep the note URL and image index.

An image-derived price stays a `PRICE_SIGNAL` like any other community figure.
Being written in a table makes it look authoritative; it is still one
traveller's receipt from one trip on one date.

Skip this on the OTA. Flight prices are in the DOM, and screenshots there cost
time without adding anything.

### Read contract

For each selected note, capture:

- Title
- Author display name when visible
- Published or updated time when visible
- Note URL
- Visible body text
- Place names
- Suggested sequence or timing, recorded as `ROUTE_HYPOTHESIS`
- Chartered-car, ticket and other cost figures, recorded as `PRICE_SIGNAL`
- Queue, closure, weather, and transport claims
- Seasonal timing such as foliage or bloom windows
- Visible engagement counts only when useful

For each major place, produce enough evidence to explain:

- What is distinctive about it
- Why it fits the user's style
- Recommended visit length
- Best time of day or season when stated
- Physical load or altitude
- Transport, queue, closure, and cost caveats

### Evidence classes

Xiaohongshu is researched for far more than destination discovery. Route
sequencing, chartered-car and ticket price levels, queue times, perceived
effort, and seasonal timing all come from here and all shape the plan. What
differs is how each claim is allowed to enter it.

Every captured claim belongs to exactly one class:

| Class | Example | How it may be used |
|---|---|---|
| `ROUTE_HYPOTHESIS` | 「这三个点一天能串完」 | A candidate ordering only. Amap computes the real travel times and the feasibility checker rules on it. |
| `TRAVEL_TIME_HINT` | 「打车过去 20 分钟」 | A hint that Amap recomputes. The Amap figure wins on any disagreement. |
| `PRICE_SIGNAL` | 「包车 200 一天」 | A market signal, never a verified price. Keep the source and timestamp, and label it as unverified in the plan. |
| `EXPERIENCE` | 「北门进人少」「索道排四十分钟」 | Usable as advice as written, attributed, with no verification step. |
| `SEASONAL` | 「枫叶十一月中旬红」 | Usable for timing advice, attributed, and flagged when the trip sits near the stated edge. |

Opening hours, ticket prices, train schedules and seat availability are never
taken from a note. Those come from the venue, Amap, or 12306, whatever a note
says.

The distinction is not a way of discarding community knowledge — it is what
lets all of it be used. A claim recorded as a hypothesis can shape the route
without ever being presented to the traveller as a fact.

Click "expand" when required. Scroll only enough to load the selected note and
a small number of relevant visible comments.

Do not:

- Download original media
- Transcribe video audio unless separately authorized and supported
- Read an entire comment corpus
- Like, collect, follow, comment, or publish
- Circumvent login, visibility, or regional restrictions

### Completion gate

Finish Xiaohongshu before opening an OTA. Save three to eight high-signal notes
or explicitly mark the phase `BLOCKED`. Do not keep scrolling to maximize note
count.

## Extraction Quality

Prefer DOM/accessibility snapshots for text. Use screenshots only for visual
content that is absent from the DOM. Mark OCR or image-derived claims separately.

Every browser result must include:

```json
{
  "channel": "provider_web",
  "login_state": "PUBLIC_READY",
  "page_visible_only": true,
  "checked_at": "ISO-8601 timestamp",
  "url": "https://...",
  "confidence": "HIGH|MEDIUM|LOW"
}
```

## Failure Handling

- Login wall: request manual login.
- CAPTCHA: request manual completion, then stop if it persists.
- Empty or virtualized list: scroll once, wait briefly, and re-snapshot.
- Page structure changed: re-snapshot; do not guess selectors.
- Price changed during refresh: replace the old value and disclose the change.
- Access blocked: mark the source unavailable and continue with remaining sources.
- Two recovery cycles without new data: stop the phase and return partial results.
