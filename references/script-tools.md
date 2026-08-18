# Script and Tool Inventory

## Persistent Scripts

### `scripts/travel_planner.py`

Commands:

- `validate-request`: check intake completeness, field validity, and explicit
  requirement conflicts before research.
- `credential-status`: check Amap Keychain configuration.
- `preflight`: verify live Amap access.
- `doctor`: check Python, Amap, rail runtime, MCP registration, and the browser
  capability reported by the invoking Agent.
- `search-places`: query normalized Amap POIs.
- `amap-snapshot`: collect locations, routes, and nearby places.
- `compile-research`: merge normalized social notes into attraction cards.
- `normalize-rail`: turn a 12306 `query-tickets` payload into comparable
  records. Seat availability mixes integers with `有` and `无`, so raw values
  must never be compared or passed to `int()`. Add `--select` to narrow to
  usable candidates.
- `validate-flights`: check browser-derived flight offers. Structural checks
  always run; freshness is compared against `--now`, which defaults to the
  current time, and `--skip-freshness` limits the run to structure alone.
- `evaluate`: run deterministic time, route, budget, and opening-hour checks.
- `validate-plan`: reject plans missing attraction content or source metadata.

### `scripts/setup_amap_key.sh`

Stores the Amap key in macOS Keychain without writing it to project files.

### `scripts/setup_rail_mcp.sh`

Installs the pinned community 12306 MCP in a per-user data directory, applies
the local security patch, and prints the stdio configuration. Pass
`--register-codex` to register it through `codex mcp add`.

### `scripts/prepare_release.sh`

Creates an allowlisted GitHub release directory. It does not copy provider
installations, virtual environments, runtime artifacts, or browser state.

### `scripts/audit_release.sh`

Fails the release when forbidden directories, sensitive files, high-confidence
secret patterns, absolute user paths, or real-looking Xiaohongshu note IDs are
found. It also runs `gitleaks` when available.

## External Agent Tools

- Browser adapter: dynamic OTA and Xiaohongshu page interaction. TRAE uses its
  built-in Browser Use capability; other clients require an equivalent tool.
- Amap Web API: called through `travel_planner.py`.
- 12306 community MCP: rail schedules, availability, prices, transfers.
- Web Search: official documentation and fallback discovery only.

## Run Artifacts

For a substantial planning run, preserve these normalized JSON artifacts in a
temporary run directory:

```text
trip_request.json
social_research.json
destination_brief.json
route_skeletons.json
rail_options.json
flight_offers.json
candidate_plans.json
feasibility_reports.json
final_plan.json
plan_validation.json
```

Do not persist cookies, passwords, SMS codes, API keys, raw request headers, or
full raw provider responses.
