# Client Compatibility

## Portability Layers

The repository contains four layers with different portability:

| Layer | Portability | Requirement |
|---|---|---|
| Data models, intake, research compiler, feasibility and plan validation | Fully portable | Python 3.9+ and shell/file access |
| Amap POI and route connector | Fully portable | Network access and `AMAP_API_KEY` or macOS Keychain |
| Community 12306 rail connector | MCP portable | Any client that supports local stdio MCP |
| OTA and Xiaohongshu research | Adapter dependent | Interactive browser automation with manual login handoff |

The Skill degrades safely. Without browser automation, users can provide
normalized `social_research.json` and `flight_offers.json`, or run map/rail-only
planning.

## Skill Installation Paths

The repository itself is the Skill directory. Clone it once, then copy or
symlink it to the client's discovery location.

### TRAE

```text
<workspace>/.trae/skills/travel-planner-mvp/
```

Status: full workflow tested with TRAE Browser Use, shell tools, Amap, and local
12306 MCP.

### Claude Code

Project scope:

```text
<workspace>/.claude/skills/travel-planner-mvp/
```

Personal scope:

```text
~/.claude/skills/travel-planner-mvp/
```

Status: full workflow live-tested with the Claude Browser tool, shell tools,
Amap, and local 12306 MCP — real 12306 queries, real Ctrip flight and hotel
pages, and real Xiaohongshu research including carousel-image reading, across
several complete planning runs. This is the client the coverage gate, the
login-handoff pattern, and the lodging login-gating rule were all discovered
on; see [`CONTRIBUTING.md`](../CONTRIBUTING.md) for what each run found.

### OpenAI Codex

Preferred installation: ask `$skill-installer` to install the GitHub repository
root as `travel-planner-mvp`. Use the absolute path returned by the installer for
all setup commands. Manual discovery paths are:

Repository scope:

```text
<workspace>/.agents/skills/travel-planner-mvp/
```

User scope:

```text
~/.agents/skills/travel-planner-mvp/
```

Status: Skill structure, `agents/openai.yaml`, and scripts are compatible.
Configure the local 12306 MCP and a browser automation tool separately. The
repository does not currently include an OpenAI plugin manifest.

### Cursor and Other Agents

Use the client's documented Agent Skills directory when it supports the open
`SKILL.md` structure. Otherwise:

1. Load `SKILL.md` as a project rule or reusable prompt.
2. Make `references/` readable to the Agent.
3. Allow execution of `scripts/travel_planner.py`.
4. Configure the local stdio 12306 MCP.
5. Provide a browser adapter satisfying `browser-use.md`.

Status: capability-compatible, but automatic Skill discovery and tool names
depend on the client and version.

## MCP Configuration

Run `bash <SKILL_ROOT>/scripts/setup_rail_mcp.sh`. The script installs the
runtime outside the Skill directory and prints a standard stdio MCP
configuration:

```json
{
  "mcpServers": {
    "12306": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/user-data-path/mcp-server-12306",
        "run",
        "mcp-server-12306"
      ]
    }
  }
}
```

Import the server using the client's MCP settings. If the client uses a
different configuration schema, preserve the same command and argument list.

For Codex, run:

```bash
bash <SKILL_ROOT>/scripts/setup_rail_mcp.sh --register-codex
codex mcp list
```

Then restart Codex. Alternatively, add the printed command and arguments as a
local STDIO server under `Settings -> MCP servers`.

## Browser Adapter Mapping

Map these logical operations to the client:

| Logical operation | Typical implementation |
|---|---|
| `list_tabs`, `activate_tab`, `close_tab` | Browser or Playwright tab/page tools |
| `observe_page` | DOM snapshot, accessibility tree, or visible page text |
| `navigate`, `click`, `type`, `select`, `scroll`, `wait` | Browser interaction tools |
| `extract_visible_data` | DOM evaluation or structured extraction |
| `request_user_handoff` | Client confirmation/user interaction mechanism |

Do not map `request_user_handoff` to automated credential entry.

## Capability Modes

### Full

Requirements:

- Skill discovery
- Shell/Python execution
- Local stdio MCP
- Interactive browser automation
- User login/CAPTCHA handoff

Provides map, rail, flight, lodging, and Xiaohongshu-assisted planning.
Lodging additionally requires the login handoff every time — unlike flights,
Ctrip shows a signed-out visitor no room price at all.

### Browserless

Requirements:

- Skill or instruction loading
- Shell/Python execution
- Optional local stdio MCP

Provides deterministic planning, Amap, and rail. Flight, lodging, and social
research must be user-provided or marked unavailable.

### Script Only

Run:

```bash
python3 <SKILL_ROOT>/scripts/travel_planner.py --help
```

Provides intake validation, Amap queries, research compilation, feasibility
evaluation, and plan validation without an Agent client.

## Known Non-Portable Parts

- `setup_amap_key.sh` uses macOS Keychain.
- Linux and Windows should supply `AMAP_API_KEY` from their own secret manager.
- The rail runtime uses a per-user data directory and survives Skill upgrades.
- Browser login persistence is client-specific.
- Native app prices are not available through generic browser automation.
- Tool names differ across browser implementations; use the logical contract,
  not TRAE-specific names.
