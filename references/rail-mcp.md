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
./scripts/setup_rail_mcp.sh
```

The script prints the absolute MCP configuration after setup. Use stdio mode.
Do not expose the optional HTTP transport or bind a network port.

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
