#!/bin/sh
set -eu

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  cat <<'EOF'
Usage: bash scripts/setup_amap_key.sh

Prompts for an Amap Web Service API key and stores it in macOS Keychain.
The key is never written to the Skill directory or printed by this script.
EOF
  exit 0
fi

if [ "$#" -ne 0 ]; then
  echo "This command does not accept arguments. Use --help for usage." >&2
  exit 2
fi

if [ "$(uname -s)" != "Darwin" ]; then
  echo "This setup helper requires macOS Keychain." >&2
  exit 1
fi

echo "Enter your Amap Web Service API key when prompted."
echo "The value will be stored in macOS Keychain and will not be printed."
security add-generic-password \
  -U \
  -s "travel-planner-mvp" \
  -a "amap-api-key" \
  -l "Travel Planner MVP Amap API Key" \
  -w

echo "Amap API key stored in macOS Keychain."
