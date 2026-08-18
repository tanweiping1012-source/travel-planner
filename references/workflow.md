# Read-Only Workflow

## State Machine

```text
COLLECT_REQUIREMENTS
  -> VALIDATE_REQUEST
  -> CLARIFY_CONSTRAINTS (only when validator requires it)
  -> SOURCE_PREFLIGHT
  -> REQUEST_BROWSER_APPROVAL
  -> SOCIAL_RESEARCH
  -> COMPILE_DESTINATION_BRIEF
  -> VALIDATE_PLACES_AND_LOCAL_ROUTES
  -> BUILD_ROUTE_SKELETONS
  -> TRANSPORT_RESEARCH
  -> ATTACH_PRICES
  -> FEASIBILITY_CHECK
  -> REPAIR_OR_RANK
  -> CONTENT_COMPLETENESS_CHECK
  -> REFRESH_DYNAMIC_DATA
  -> PRESENT
```

Never let raw provider responses enter candidate generation.
Do not perform Xiaohongshu and OTA browser research concurrently.

## Intake Gate

1. Normalize the initial user message or README form into `trip_request.json`.
2. Run `validate-request`.
3. When status is `READY`, proceed without repeating any intake question.
4. When status is `NEEDS_CLARIFICATION`, ask one batched question containing
   every returned missing field and conflict.
5. When status is `INVALID`, request corrected values before source research.
6. Ask again later only when live evidence introduces a new material conflict.

Examples of new material conflicts include:

- A `CORE` place is closed or legally inaccessible.
- A route exceeds the stated mobility or altitude limit.
- The only feasible route exceeds the stated budget.
- A weather-dependent core experience conflicts with the user's declared risk
  tolerance.
- A required login mode exceeds the approved Browser Use scope.

Do not ask about lower-value optional preferences when a labeled assumption can
resolve them. Safety and legal access never become optional trade-offs.

## Source Preflight

Return one status per connector:

```text
READY
PUBLIC_READY
LOGIN_REQUIRED
CONNECTED
EXPIRED
DEGRADED
BLOCKED
UNAVAILABLE
```

Required checks:

- Amap credential exists and one live POI request succeeds.
- The local 12306 MCP lists its expected read-only tools.
- OTA and Xiaohongshu access matches the validated provider-specific approval.
- Browser session state is observed, never assumed.

## Phase 1: Destination Research

Xiaohongshu is a discovery input, so it must run before transport pricing.

1. Search style, duration, public-transport, and risk-oriented queries.
2. Start anonymously and request manual login only when the page requires it.
3. Read three to eight high-signal notes.
4. Extract place names, timing advice, queue reports, and risk claims.
5. Preserve every selected note URL and normalize the evidence.
6. Finish or explicitly stop the Xiaohongshu phase.
7. Compile results with `compile-research`.
8. Produce a `DestinationBrief` containing:
   - Candidate places
   - Defining features
   - Why each place fits the requested style
   - Suggested duration and best time
   - Physical load and accessibility concerns
   - Transport and queue claims
   - Source URLs and confidence

The phase is incomplete when it only produces place names.

## Phase 2: Place and Route Validation

### Map branch

1. Resolve origin, destination, airports, stations, and candidate places.
2. Reject closed or ambiguous POIs.
3. Validate every selected place from the destination brief.
4. Group nearby places into coherent day clusters.
5. Query every local route needed by a candidate.

Do not ask the OTA for prices until at least one route skeleton exists.

## Phase 3: Transport Research

### Rail branch

1. Resolve station names with `search-stations`.
2. Query direct availability with `query-tickets`.
3. Query exact fares with `query-ticket-price`.
4. Query transfers only when direct service is unsuitable.
5. Normalize every payload with `normalize-rail` before reading any seat
   value. Availability mixes integers with `有` and `无`, so comparing the raw
   values is unsafe and `int()` raises on the words.
6. Map a selected train into an **activity**, not a segment. The journey time
   belongs to the ride itself; reaching the station is a separate segment
   measured by the map provider.
7. Keep the MCP source label and query timestamp.

### Flight branch

This branch starts only after the social browser phase is complete and the
route skeleton identifies the required gateway city and time windows.

1. Use Browser Use on an approved OTA web domain.
2. Start with the route skeleton's gateway and arrival/departure deadlines.
3. Search exact airports or city groups, dates, travelers, and cabin.
4. Extract visible offers only.
5. Retain channel, login state, baggage visibility, and timestamp.
6. Reject cheap offers that break downstream transfers.
7. Never interpret a monthly-low-price page as the requested live fare.
8. Run `validate-flights` before any offer influences a candidate. It rejects
   a leg whose arrival precedes its departure, flags a stated duration that
   disagrees with the clock, and requires the unguaranteed-price caveat.
9. Map a selected flight into an **activity** carrying the check-in buffer,
   120 minutes domestic and 180 international.

## Browser Phase Gate

Use one browser worker and one dynamic site at a time:

```text
XIAOHONGSHU_OPEN
  -> XIAOHONGSHU_DONE | XIAOHONGSHU_BLOCKED
  -> SAVE_SOCIAL_RESEARCH
  -> CLOSE_OR_FREEZE_XIAOHONGSHU_TABS
  -> OTA_OPEN
  -> OTA_DONE | OTA_BLOCKED
  -> SAVE_FLIGHT_RESEARCH
```

Do not spawn a second browser worker to recover while the first worker is still
active. Instead, set a bounded phase budget and ask the same worker to return
partial results.

Recommended budgets:

- Login handoff: wait for the user without running another browser phase.
- Xiaohongshu: three focused queries, three to eight notes, then stop.
- OTA initial search: up to ten representative offers.
- OTA targeted follow-up: one additional time-window filter.
- A phase with no progress after two snapshot/recovery cycles becomes `BLOCKED`.

## Candidate Generation

Always build:

- Economy: lowest expected total cost that remains feasible.
- Balanced: best trade-off among cost, time, and style.
- Relaxed: fewer moves, larger buffers, and lower daily load.

Do not force three materially identical candidates.

Each day must answer:

- Where does the traveler go?
- What are the defining features of each major place?
- Why is it included for this travel style?
- How long should the traveler stay?
- How does the traveler move to the next place?
- What is the physical load and major caveat?

A timeline containing only transport segments is invalid.

## Feasibility and Repair

Run the deterministic engine. Repair in this order:

1. Adjust activity times.
2. Increase transfer buffers.
3. Change transport option.
4. Swap adjacent places.
5. Move an optional place to another day.
6. Remove the lowest-priority optional place.

Stop after three repair attempts. Preserve infeasible candidates only when they
help explain a trade-off.

## Content Completeness

Run `validate-plan` before presentation. A plan fails when:

- It has no attraction day.
- A major attraction has no features or reason to visit.
- A day has no activity description.
- A transition between consecutive activities has no transport segment.
- Browser-derived prices lack channel or timestamp.

Do not present an invalid plan as complete.

## Dynamic Refresh

Immediately before presentation:

- Re-query shortlisted rail options.
- Re-open or refresh shortlisted flight results.
- Re-run `validate-flights` with the presentation time. `STALE_FLIGHT_PRICE`
  means the offer must be looked up again, not relabelled: the default limit
  is two hours, because a rail fare barely moves while an airfare from this
  morning may already be wrong.
- Re-run affected transfer checks if times or airports changed.
- Mark a result stale when refresh fails.

## Failure Policy

- Missing API key: stop live-map planning and explain how to configure it.
- Amap authentication error: retry at most once.
- Rail MCP blocked: fall back to read-only 12306 Browser Use only with approval.
- OTA login required: ask the user to take control; never type credentials.
- Xiaohongshu login required: ask the user to scan or log in manually.
- Missing social results: continue with map and official sources, and disclose the gap.
- Route unavailable: mark the candidate infeasible; never invent duration.
- Stale price or schedule: label it as reference-only and request a refresh.
- Captcha or blocked page: stop browser automation; do not bypass it.
- Browser and API sources conflict: keep both and explain the conflict.

## Safety Boundary

This workflow is read-only. It must never purchase, reserve, pay, publish,
comment, like, follow, or modify an external account.
