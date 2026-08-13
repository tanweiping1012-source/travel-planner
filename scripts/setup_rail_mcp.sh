#!/bin/sh
set -eu

UPSTREAM_URL="https://github.com/drfccv/mcp-server-12306.git"
UPSTREAM_COMMIT="1b6ee94ff801cbfe0c1e8c8bb95195466b08b6dd"
REGISTER_CODEX=0

usage() {
  cat <<'EOF'
Usage: bash scripts/setup_rail_mcp.sh [--register-codex]

Installs the pinned, patched 12306 community MCP outside the Skill directory.
Set TRAVEL_PLANNER_DATA_DIR to override the per-user data location.

Options:
  --register-codex  Register the installed stdio server with Codex.
  -h, --help        Show this help.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --register-codex)
      REGISTER_CODEX=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
SKILL_ROOT=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)
PATCH_FILE="$SKILL_ROOT/patches/mcp-server-12306-security.patch"

if [ -n "${TRAVEL_PLANNER_DATA_DIR:-}" ]; then
  DATA_ROOT=$TRAVEL_PLANNER_DATA_DIR
elif [ "$(uname -s)" = "Darwin" ]; then
  : "${HOME:?HOME is required to resolve the user data directory}"
  DATA_ROOT="$HOME/Library/Application Support/travel-planner-mvp"
else
  : "${HOME:?HOME is required to resolve the user data directory}"
  DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
  DATA_ROOT="$DATA_HOME/travel-planner-mvp"
fi

case "$DATA_ROOT" in
  /*) ;;
  *)
    echo "TRAVEL_PLANNER_DATA_DIR must resolve to an absolute path." >&2
    exit 1
    ;;
esac

CHECKOUT_DIR="$DATA_ROOT/mcp-server-12306"

if ! command -v git >/dev/null 2>&1; then
  echo "git is required." >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required to run the pinned Python 3.10+ MCP environment." >&2
  echo "Install it first, for example: brew install uv" >&2
  exit 1
fi

UV_COMMAND=$(command -v uv)
mkdir -p "$DATA_ROOT"

if [ ! -d "$CHECKOUT_DIR/.git" ]; then
  if [ -e "$CHECKOUT_DIR" ]; then
    echo "Refusing to replace non-git path: $CHECKOUT_DIR" >&2
    exit 1
  fi
  git clone --no-checkout "$UPSTREAM_URL" "$CHECKOUT_DIR"
fi

CURRENT_REMOTE=$(git -C "$CHECKOUT_DIR" remote get-url origin)
if [ "$CURRENT_REMOTE" != "$UPSTREAM_URL" ]; then
  echo "Unexpected upstream remote: $CURRENT_REMOTE" >&2
  exit 1
fi

git -C "$CHECKOUT_DIR" fetch --depth 1 origin "$UPSTREAM_COMMIT"
git -C "$CHECKOUT_DIR" checkout --detach "$UPSTREAM_COMMIT"

if git -C "$CHECKOUT_DIR" apply --reverse --check "$PATCH_FILE" >/dev/null 2>&1; then
  echo "Security patch already applied."
else
  git -C "$CHECKOUT_DIR" apply --check "$PATCH_FILE"
  git -C "$CHECKOUT_DIR" apply "$PATCH_FILE"
fi

"$UV_COMMAND" sync --directory "$CHECKOUT_DIR"
"$UV_COMMAND" --directory "$CHECKOUT_DIR" run mcp-server-12306 --version

printf '\nInstalled runtime: %s\n' "$CHECKOUT_DIR"
printf '\nAdd this MCP configuration using the absolute path shown below:\n\n'
printf '{\n'
printf '  "mcpServers": {\n'
printf '    "12306": {\n'
printf '      "command": "%s",\n' "$UV_COMMAND"
printf '      "args": ["--directory", "%s", "run", "mcp-server-12306"]\n' "$CHECKOUT_DIR"
printf '    }\n'
printf '  }\n'
printf '}\n'

if [ "$REGISTER_CODEX" -eq 1 ]; then
  if ! command -v codex >/dev/null 2>&1; then
    echo "Codex CLI is unavailable; add the stdio server in Codex Settings -> MCP servers." >&2
    exit 1
  fi
  if codex mcp get 12306 >/dev/null 2>&1; then
    echo "Codex already has an MCP server named 12306; leaving it unchanged." >&2
    echo "Remove it first with: codex mcp remove 12306" >&2
    exit 1
  fi
  codex mcp add 12306 -- "$UV_COMMAND" \
    --directory "$CHECKOUT_DIR" run mcp-server-12306
  codex mcp get 12306
  echo "Restart Codex before using the new MCP tools."
else
  printf '\nCodex CLI registration command:\n\n'
  printf 'codex mcp add 12306 -- %s --directory "%s" run mcp-server-12306\n' \
    "$UV_COMMAND" "$CHECKOUT_DIR"
fi
