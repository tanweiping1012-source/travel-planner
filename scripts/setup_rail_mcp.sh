#!/bin/sh
set -eu

UPSTREAM_URL="https://github.com/drfccv/mcp-server-12306.git"
UPSTREAM_COMMIT="1b6ee94ff801cbfe0c1e8c8bb95195466b08b6dd"

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
VENDOR_ROOT="$SKILL_ROOT/vendor"
CHECKOUT_DIR="$VENDOR_ROOT/mcp-server-12306"
PATCH_FILE="$SKILL_ROOT/patches/mcp-server-12306-security.patch"

if ! command -v git >/dev/null 2>&1; then
  echo "git is required." >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required to run the pinned Python 3.10+ MCP environment." >&2
  echo "Install it first, for example: brew install uv" >&2
  exit 1
fi

mkdir -p "$VENDOR_ROOT"

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

uv sync --directory "$CHECKOUT_DIR"
uv --directory "$CHECKOUT_DIR" run mcp-server-12306 --version

printf '\nAdd this MCP configuration using the absolute path shown below:\n\n'
printf '{\n'
printf '  "mcpServers": {\n'
printf '    "12306": {\n'
printf '      "command": "uv",\n'
printf '      "args": ["--directory", "%s", "run", "mcp-server-12306"]\n' "$CHECKOUT_DIR"
printf '    }\n'
printf '  }\n'
printf '}\n'
