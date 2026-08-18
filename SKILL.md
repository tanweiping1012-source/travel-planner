---
name: "travel-planner-mvp"
description: "Create evidence-backed, read-only travel plans using Amap, a community 12306 rail MCP, and approved browser research. Use for 行程规划、路线安排、景点取舍、高铁或机票比较、预算分析、旅行可行性检查，以及中国境内多城市旅行规划。"
---

# Travel Planner MVP

Create evidence-based travel plans without purchasing, booking, paying, or
changing any external account.

## Resolve the Skill root

Treat the directory containing this `SKILL.md` as `SKILL_ROOT`. Resolve it to an
absolute path before running commands. Never assume the current working
directory is the Skill directory. Run the CLI as:

```bash
python3 "$SKILL_ROOT/scripts/travel_planner.py" <command>
```

Use absolute paths for every input and output file. Keep run artifacts outside
`SKILL_ROOT`; use a temporary directory or the user's workspace.

## Enforce read-only boundaries

- Never purchase, reserve, pay, submit an order, join a waitlist, change, or
  cancel a booking.
- Never type passwords, SMS codes, identity documents, payment data, or API
  keys. Hand login and CAPTCHA interaction to the user.
- Never export cookies, tokens, request headers, signed URLs, or browser state.
- Never bypass a CAPTCHA, login wall, anti-bot control, or security warning.
- Never like, follow, collect, comment, publish, or modify an external account.
- Never describe the community 12306 MCP as official or commercially
  authorized.
- Never invent routes, schedules, prices, opening hours, or availability.
- Time-stamp all dynamic data and keep facts separate from recommendations.

## Load references progressively

Read only the references needed for the current task:

- Read [workflow](references/workflow.md) for every end-to-end planning task.
- Read [intake template](references/intake-template.md) when collecting or
  normalizing trip requirements.
- Read [data contracts](references/data-contracts.md) before creating or
  validating JSON artifacts.
- Read [rail MCP](references/rail-mcp.md) only when rail research or setup is
  needed.
- Read [browser contract](references/browser-use.md) only when researching
  Xiaohongshu or an OTA.
- Read [client compatibility](references/client-compatibility.md) only during
  installation, capability mapping, or troubleshooting.
- Read [script inventory](references/script-tools.md) only when command details
  or artifact names are needed.

## Validate intake

Normalize the user's request into `trip_request.json`, then run:

```bash
python3 "$SKILL_ROOT/scripts/travel_planner.py" \
  validate-request --input /absolute/path/to/trip_request.json
```

Follow the returned status:

- `READY`: continue without re-asking populated fields.
- `NEEDS_CLARIFICATION`: ask once for all `missing_fields` and `conflicts`.
- `INVALID`: report invalid fields and request corrected values before research.

Treat `CORE` places as non-removable unless safety, legal access, closure,
weather, altitude, or physical feasibility makes them impossible. Handle
optional preferences with labeled assumptions. Ask a second question only when
new live evidence creates a material conflict that intake could not reveal.

## Run capability diagnostics

Report the browser capability that the current Agent actually has, then run:

```bash
python3 "$SKILL_ROOT/scripts/travel_planner.py" doctor \
  --live --client codex --browser-status available
```

Use `unavailable` when no interactive browser exists and `unknown` when the
client cannot determine it. Follow the returned `actions`. Never ask the user to
paste an API key into chat; direct macOS users to
`bash "$SKILL_ROOT/scripts/setup_amap_key.sh"` and let them enter it locally.

Degrade safely when optional capabilities are missing:

- Without rail MCP, omit live rail claims or use an approved read-only browser.
- Without browser automation, accept normalized social/flight JSON from the
  user or mark those channels unavailable.
- Without Amap, do not claim verified POIs or ground routes.

## Execute the planning workflow

1. Validate intake and resolve only reported gaps.
2. Run `doctor` and record capability limitations.
3. Use anonymous browser sessions first; hand login or CAPTCHA to the user.
4. Run Xiaohongshu research alone, then close or isolate it before opening an
   OTA.
5. Compile social evidence into attraction cards.
6. Validate candidate places and local routes with Amap.
7. Build route skeletons before querying long-distance prices.
8. Query rail with the community MCP, then query flights in a separate browser
   phase.
9. Normalize every result before it affects planning.
10. Construct economy, balanced, and relaxed candidates when they are genuinely
    different.
11. Obtain a real route for every consecutive place pair.
12. Run deterministic feasibility evaluation for each candidate.
13. Repair hard conflicts and re-evaluate at most three times.
14. Validate final plan content.
15. Refresh selected rail and flight options immediately before presentation.

Do not skip source normalization, route verification, feasibility evaluation,
content validation, or the final refresh of dynamic transport data.

## Use deterministic commands

Compile normalized social research:

```bash
python3 "$SKILL_ROOT/scripts/travel_planner.py" \
  compile-research \
  --input /absolute/path/to/social_research.json \
  --output /absolute/path/to/destination_brief.json
```

Normalize a 12306 `query-tickets` payload before reading any seat value:

```bash
python3 "$SKILL_ROOT/scripts/travel_planner.py" \
  normalize-rail \
  --input /absolute/path/to/rail_query.json \
  --select --seat-class second_class --limit 5 \
  --output /absolute/path/to/rail_candidates.json
```

Seat availability mixes integers with `有` and `无`, so never compare the raw
values. A train ride becomes an *activity*; the ride to the station is a
separate segment whose duration comes from Amap.

Evaluate an itinerary:

```bash
python3 "$SKILL_ROOT/scripts/travel_planner.py" \
  evaluate \
  --input /absolute/path/to/itinerary.json \
  --output /absolute/path/to/feasibility_report.json
```

Validate final content:

```bash
python3 "$SKILL_ROOT/scripts/travel_planner.py" \
  validate-plan --input /absolute/path/to/final_plan.json
```

The scripts return structured JSON. Consume the JSON directly; do not parse
terminal prose with regular expressions.

## Apply source rules

- Use Amap for normalized POIs, coordinates, and returned ground routes.
- Label rail results `12306-community-mcp` and retain the connector version.
- Label flight results with the exact OTA web channel and login state.
- Treat Xiaohongshu as inspiration and experience evidence, not route or
  opening-hours authority.
- Retain source URL, query time, channel, login state, and confidence.
- Prefer official venue information when opening hours or rules conflict.
- State missing evidence and reduce confidence instead of estimating facts.

## Return the plan

Include:

1. Assumptions and constraints.
2. Economy, balanced, and relaxed options when materially different.
3. Day-by-day timelines, route modes, and transfer buffers.
4. For every major attraction: defining features, why to visit, suggested
   duration, best time, physical load, and source-backed caveats.
5. Reference costs, channels, and query timestamps.
6. Feasibility status, hard conflicts, warnings, and adjustments.
7. Source links and connector labels.
8. Login/channel caveats for browser-derived prices.
9. Items the user must verify before departure.

Keep verified facts and planning recommendations visibly separate.
