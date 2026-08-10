#!/bin/sh
set -eu

if [ "$(uname -s)" != "Darwin" ]; then
  echo "This setup helper requires macOS Keychain." >&2
  exit 1
fi

echo "Enter the regenerated Amap Web Service API key when prompted."
echo "The value will be stored in macOS Keychain and will not be printed."
security add-generic-password \
  -U \
  -s "trae-travel-planner" \
  -a "amap-api-key" \
  -l "TRAE Travel Planner Amap API Key" \
  -w

echo "Amap API key stored in macOS Keychain."
