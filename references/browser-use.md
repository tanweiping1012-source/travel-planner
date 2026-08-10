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
4. Prefer visible DOM/accessibility text over screenshots.
5. Use screenshots only when meaningful information is visual-only.
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

1. Stop browser actions.
2. Hand control to the user with the dedicated user-interaction tool when available.
3. Ask the user to log in or complete the challenge manually.
4. Resume only after a fresh snapshot confirms the resulting state.

Never type a password, SMS code, identity number, or payment value.

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

### Collection limit

- Collect enough results to represent cheapest, fastest, and balanced choices.
- Prefer 10 to 20 normalized offers, not an unbounded result crawl.
- Use a second OTA only to resolve material conflicts or missing coverage.
- Perform at most one targeted follow-up for a required time window.

## Xiaohongshu Research

### Anonymous mode

Try public search or user-provided share links first. Anonymous pages can expose
titles and some full note bodies, but coverage is not guaranteed.

### Login mode

Stable search, expanded bodies, and visible comments may require manual login.
Use a separate browser context from the OTA session.

### Read contract

For each selected note, capture:

- Title
- Author display name when visible
- Published or updated time when visible
- Note URL
- Visible body text
- Place names
- Suggested sequence or timing
- Queue, closure, weather, and transport claims
- Visible engagement counts only when useful

For each major place, produce enough evidence to explain:

- What is distinctive about it
- Why it fits the user's style
- Recommended visit length
- Best time of day or season when stated
- Physical load or altitude
- Transport, queue, closure, and cost caveats

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
