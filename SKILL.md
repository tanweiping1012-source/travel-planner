---
name: "travel-planner-mvp"
description: "Builds read-only travel plans with live maps, rail MCP, and browser research. Invoke for itinerary, route, fare comparison, or feasibility requests."
---

# Travel Planner MVP

Create evidence-based, read-only travel plans with four data channels:

- Amap Web API for POIs, coordinates, and ground routes.
- A locally patched 12306 community MCP for rail schedules, fares, and availability.
- An approved browser automation capability for current visible OTA flight offers.
- An approved browser automation capability for Xiaohongshu public notes and
  user-authorized visible content.

Use Web Search only for official documentation and fallback discovery. Never use
search snippets as live fare, availability, opening-hours, or route evidence.

## Hard Boundaries

- Never purchase, reserve, pay, or submit an external transaction.
- Never type passwords, SMS codes, identity documents, or payment data.
- Never export or expose browser cookies, API keys, tokens, request headers, or signed URLs.
- Never bypass a CAPTCHA, login wall, anti-bot control, or browser security warning.
- Never like, follow, collect, comment, publish, or modify an external account.
- Never claim that a community 12306 MCP is official or commercially authorized.
- Never invent a route, schedule, price, opening time, or availability.
- Treat all dynamic data as time-stamped reference information.

## Required Inputs

Prefer the complete intake template in [README](README.md). Collect:

- Origin and core destination
- Start and end dates
- Number of travelers
- Budget and whether it is per-person or party-total
- Travel style
- Required places with `CORE`, `IMPORTANT`, or `OPTIONAL` priority
- Excluded places
- Mobility level, walking limit, high-altitude acceptance, and accessibility needs
- Trade-off priority among core places, cost, pace, and comfort
- Acceptance of weather-dependent core experiences
- Xiaohongshu and OTA read-only browser approval
- Latest-return and transport constraints when relevant

Read [data contracts](references/data-contracts.md) before constructing JSON.

## Intake and Question Policy

Normalize the user's initial message into `trip_request.json`, then run:

```bash
python scripts/travel_planner.py \
  validate-request --input /absolute/path/to/trip_request.json
```

Follow the returned status:

- `READY`: start source preflight. Do not ask again about any populated field.
- `NEEDS_CLARIFICATION`: ask once for all `missing_fields` and `conflicts`.
  Do not split them across multiple conversational turns.
- `INVALID`: report the invalid fields and request corrected values before research.

Additional question rules:

- Treat a `CORE` place as non-removable. Adjust optional places, comfort, pace,
  or cost according to `tradeoff_priority`.
- Safety and legal access always override user trade-off priority.
- Ask a second question only when new live evidence creates a material conflict
  that could not have been known during intake, such as a closure, altitude
  mismatch, unavailable night descent, or budget overrun caused by the only
  feasible route.
- Do not ask for optional preferences that can be handled by clearly labeled
  assumptions.
- Browser approval included in a valid request satisfies the one-time approval
  requirement for the named provider. Do not request it again unless the scope
  or login mode changes.

## Mandatory Preflight

Read all of these references before research:

- [workflow](references/workflow.md)
- [rail MCP](references/rail-mcp.md)
- [browser capability contract](references/browser-use.md)
- [client compatibility](references/client-compatibility.md)
- [data contracts](references/data-contracts.md)
- [script and tool inventory](references/script-tools.md)

Then:

1. Validate the normalized request and apply the Intake and Question Policy.
2. Resolve only the missing fields or conflicts returned by the validator.
3. Check Amap and rail MCP readiness.
4. Confirm that read-only browser approval covers the named providers.
   Do not re-ask when the validated request already contains approval.
5. Use anonymous browser sessions first.
6. Hand control to the user when login or CAPTCHA interaction is required.
7. Run Xiaohongshu research alone; do not open an OTA concurrently.
8. Compile social results into a destination brief with attraction cards.
9. Validate candidate places and local routes with Amap.
10. Build route skeletons before querying any long-distance price.
11. Query rail with MCP and then query OTA flights in a separate browser phase.
12. Normalize every result before it can affect planning.
13. Construct economy, balanced, and relaxed candidates.
14. Obtain a real route for every consecutive place pair.
15. Run deterministic feasibility evaluation for every candidate.
16. Repair hard conflicts and re-evaluate at most three times.
17. Validate itinerary content completeness.
18. Refresh selected rail and flight options immediately before presentation.

Do not skip source preflight, normalization, refresh, or feasibility evaluation.

## Setup Commands

Store the Amap Web Service API key in macOS Keychain:

```bash
./scripts/setup_amap_key.sh
```

Install the pinned, locally patched 12306 MCP:

```bash
./scripts/setup_rail_mcp.sh
```

Run all commands from the Skill root directory. Use an activated virtual
environment when desired:

```bash
python scripts/travel_planner.py \
  validate-request --input /absolute/path/to/trip_request.json
python scripts/travel_planner.py \
  credential-status
python scripts/travel_planner.py \
  preflight
```

Compile normalized social research into a destination brief:

```bash
python scripts/travel_planner.py \
  compile-research --input /absolute/path/to/social_research.json \
  --output /absolute/path/to/destination_brief.json
```

Validate that a final plan contains meaningful attraction content:

```bash
python scripts/travel_planner.py \
  validate-plan --input /absolute/path/to/plan.json
```

The scripts return structured JSON. Do not parse human-readable terminal output
with regular expressions.

## Source Rules

- Use Amap for normalized POIs, coordinates, and returned routes.
- Label rail results `12306-community-mcp`; do not label the connector official.
- Label flight results with the exact OTA web channel and login state.
- Treat Xiaohongshu as inspiration and experience evidence, not route authority.
- Retain source URL, query time, channel, login state, and confidence.
- Prefer official venue information when opening hours or rules conflict.
- State missing evidence and reduce confidence instead of estimating facts.

## Output

Return:

1. Assumptions and constraints
2. Economy, balanced, and relaxed options
3. Day-by-day timeline and route modes
4. For every major attraction: why visit, defining features, suggested duration,
   physical load, best time, and source-backed caveats
5. Reference costs and query timestamps
6. Feasibility status, hard conflicts, and warnings
7. Source links and connector labels
8. Login/channel caveats for browser-derived prices
9. Items the user must verify before departure

Keep facts and recommendations visibly separate.
