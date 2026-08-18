# Rail MCP

## Selected Project

Use `drfccv/mcp-server-12306` at the pinned commit recorded by
`scripts/setup_rail_mcp.sh`.

The connector is a community project. It directly calls public endpoints used by
the 12306 website. It is not an official developer API or an authorized sales
channel.

## Data Flow

```text
Agent
  -> local MCP over stdio
  -> kyfw.12306.cn public query endpoints
  -> local normalization
  -> Agent
```

It does not need a user account. It creates an anonymous HTTP session by loading
the public left-ticket page before each query.

## Allowed Tools

- `search-stations`
- `query-tickets`
- `query-ticket-price`
- `query-transfer`
- `get-train-route-stations`
- `get-train-no-by-train-code`
- `get-current-time`

Never add login, order, passenger, purchase, refund, or waitlist operations.

## Local Configuration

Run:

```bash
bash <SKILL_ROOT>/scripts/setup_rail_mcp.sh
```

The script installs the runtime under the user's data directory, not inside the
Skill. Set `TRAVEL_PLANNER_DATA_DIR` to override that absolute location. It
prints the absolute MCP configuration after setup. Use stdio mode. Do not expose
the optional HTTP transport or bind a network port.

For Codex, pass `--register-codex`, run `codex mcp list`, and restart Codex.

For Claude Code, add the stdio server to the `mcpServers` object in
`~/.claude.json` and restart the client:

```json
{
  "mcpServers": {
    "12306": {
      "type": "stdio",
      "command": "/absolute/path/to/uv",
      "args": ["--directory", "<CHECKOUT_DIR>", "run", "mcp-server-12306"]
    }
  }
}
```

`<CHECKOUT_DIR>` is the path printed by the setup script. Confirm the result
with `travel_planner.py doctor`, which detects the running client on its own.

## Interpreting Results

`query-tickets` reports seat availability the way 12306 does, mixing integers
with words in a single field: an exact count while twenty or fewer remain,
`有` once supply is comfortable, and `无` when a class is sold out. Never call
`int()` on these values directly. Route every payload through
`travel_planner.py normalize-rail`, which turns each value into a record
carrying `status`, `count`, and `at_least` so candidates stay comparable.

`query-tickets` carries **no fare**. A price must come from the separate
`query-ticket-price` tool, and a plan may not state a fare that was never
looked up.

A city query returns every co-located station, so do not filter by station
name. A neighbouring station is often faster than the one the traveller named.

## Security Patch

The setup process must:

- Pin a reviewed upstream commit.
- Enable TLS certificate verification.
- Remove raw response bodies from error logs.
- Avoid logging complete tool arguments.
- Keep execution local.

Do not replace the patched checkout with an unpinned `uvx` package invocation.

## Query Sequence

For each origin, destination, and date:

1. Resolve stations.
2. Query direct tickets.
3. Query prices for viable trains.
4. Query transfers only when needed.
5. Normalize to `RailOption`.
6. Refresh selected options before final output.

## Rate Policy

- At most one new 12306 request per second.
- Cache identical station/date queries for one to five minutes.
- Retry network failures at most twice with backoff.
- Stop on CAPTCHA, block, or repeated non-JSON responses.

## Limitations

- Query dates are constrained by the 12306 sale/query window.
- Station data is bundled by the upstream package and can become stale.
- Endpoint paths and response formats can change without notice.
- The upstream license is MIT, but its README disclaims commercial use.
- Production or commercial use requires separate legal and platform review.

## Provenance

Every normalized result must include:

```json
{
  "provider": "12306",
  "connector": "drfccv/mcp-server-12306",
  "connector_type": "community_mcp",
  "official_connector": false,
  "read_only": true,
  "checked_at": "ISO-8601 timestamp"
}
```
