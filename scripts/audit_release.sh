#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
SKILL_ROOT=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)
TARGET=${1:-"$SKILL_ROOT"}
FAILURES=0
AUDIT_TEMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/travel-planner-audit.XXXXXX")

cleanup() {
  rm -rf "$AUDIT_TEMP_DIR"
}

trap cleanup EXIT HUP INT TERM

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  FAILURES=$((FAILURES + 1))
}

if [ ! -d "$TARGET" ]; then
  echo "Audit target does not exist: $TARGET" >&2
  exit 1
fi

TARGET=$(CDPATH='' cd -- "$TARGET" && pwd)

for name in vendor .venv venv runs artifacts output; do
  if find "$TARGET" -type d -name "$name" -print -quit | grep -q .; then
    fail "forbidden directory found: $name"
  fi
done

if find "$TARGET" -type d -name .git \
  ! -path "$TARGET/.git" -print -quit | grep -q .; then
  fail "nested .git directory found"
fi

for pattern in '.env' '.env.*' '*.pem' '*.key' '*.p12' '*.pfx' '*.har' \
  '*cookie*' '*session*' 'storage-state*.json' '*.log'; do
  if find "$TARGET" -type f -name "$pattern" \
    ! -path "$TARGET/.git/*" \
    ! -name '.env.example' -print -quit | grep -q .; then
    fail "sensitive file pattern found: $pattern"
  fi
done

if find "$TARGET" -type f \
  ! -name '*.pyc' \
  ! -path "$TARGET/.git/*" \
  ! -path '*/__pycache__/*' \
  ! -name 'audit_release.sh' \
  -print0 | xargs -0 grep -nE \
    'AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{20,}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----' \
    >"$AUDIT_TEMP_DIR/secrets.txt" 2>/dev/null; then
  cat "$AUDIT_TEMP_DIR/secrets.txt" >&2
  fail "high-confidence secret pattern found"
fi

if find "$TARGET" -type f \
  ! -name '*.pyc' \
  ! -path "$TARGET/.git/*" \
  ! -path '*/__pycache__/*' \
  ! -name 'audit_release.sh' \
  -print0 | xargs -0 grep -niE \
    "AMAP(_API)?_KEY[[:space:]]*[:=][[:space:]]*['\"]?[A-Za-z0-9]{20,}" \
    >"$AUDIT_TEMP_DIR/amap-secrets.txt" 2>/dev/null; then
  cat "$AUDIT_TEMP_DIR/amap-secrets.txt" >&2
  fail "possible Amap API key assignment found"
fi

if find "$TARGET" -type f \
  ! -name '*.pyc' \
  ! -path "$TARGET/.git/*" \
  ! -path '*/__pycache__/*' \
  ! -name 'audit_release.sh' \
  -print0 | xargs -0 grep -nE \
    '/Users/[^/]+/|/home/[^/]+/|[A-Za-z]:\\\\Users\\\\[^\\\\]+' \
    >"$AUDIT_TEMP_DIR/paths.txt" 2>/dev/null; then
  cat "$AUDIT_TEMP_DIR/paths.txt" >&2
  fail "absolute user path found"
fi

if find "$TARGET" -type f \
  ! -name '*.pyc' \
  ! -path "$TARGET/.git/*" \
  ! -path '*/__pycache__/*' \
  ! -name 'audit_release.sh' \
  -print0 | xargs -0 grep -nE \
    'xiaohongshu\.com/explore/[0-9a-f]{20,}' \
    >"$AUDIT_TEMP_DIR/xhs.txt" 2>/dev/null; then
  cat "$AUDIT_TEMP_DIR/xhs.txt" >&2
  fail "real-looking Xiaohongshu note ID found"
fi

if find "$TARGET" -type f \
  ! -name '*.pyc' \
  ! -path "$TARGET/.git/*" \
  ! -path '*/__pycache__/*' \
  ! -name 'audit_release.sh' \
  -print0 | xargs -0 grep -nE \
    '2026-09-(24|27)|"budget_cny"[[:space:]]*:[[:space:]]*4000' \
    >"$AUDIT_TEMP_DIR/private-examples.txt" 2>/dev/null; then
  cat "$AUDIT_TEMP_DIR/private-examples.txt" >&2
  fail "private planning fingerprint found"
fi

if command -v gitleaks >/dev/null 2>&1; then
  gitleaks dir --redact --exit-code 1 "$TARGET" \
    >/dev/null || fail "gitleaks detected a possible secret"
else
  printf 'WARNING: gitleaks is not installed; built-in checks only.\n' >&2
fi

if [ "$FAILURES" -ne 0 ]; then
  printf 'Release audit failed with %s issue(s).\n' "$FAILURES" >&2
  exit 1
fi

printf 'Release audit passed: %s\n' "$TARGET"
