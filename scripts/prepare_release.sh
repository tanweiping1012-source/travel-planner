#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
SKILL_ROOT=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)
OUTPUT_DIR=${1:-"$SKILL_ROOT/dist/travel-planner-mvp"}

case "$OUTPUT_DIR" in
  "$SKILL_ROOT"|"$SKILL_ROOT/"*)
    case "$OUTPUT_DIR" in
      "$SKILL_ROOT/dist"|"$SKILL_ROOT/dist/"*) ;;
      *)
        echo "Output inside the skill directory is only allowed under dist/." >&2
        exit 1
        ;;
    esac
    ;;
esac

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

copy_file() {
  source_path="$SKILL_ROOT/$1"
  destination_path="$OUTPUT_DIR/$1"
  if [ ! -f "$source_path" ]; then
    echo "Required release file is missing: $1" >&2
    exit 1
  fi
  mkdir -p "$(dirname "$destination_path")"
  cp "$source_path" "$destination_path"
}

copy_tree() {
  source_path="$SKILL_ROOT/$1"
  destination_path="$OUTPUT_DIR/$1"
  if [ ! -d "$source_path" ]; then
    echo "Required release directory is missing: $1" >&2
    exit 1
  fi
  mkdir -p "$destination_path"
  find "$source_path" -type f \
    ! -name '*.pyc' \
    ! -name '.DS_Store' \
    ! -path '*/__pycache__/*' \
    -print | while IFS= read -r file; do
      relative=${file#"$source_path/"}
      mkdir -p "$destination_path/$(dirname "$relative")"
      cp "$file" "$destination_path/$relative"
    done
}

copy_file ".gitignore"
copy_file ".gitleaks.toml"
copy_file "SKILL.md"
copy_file "README.md"
copy_file "SECURITY.md"
copy_file "THIRD_PARTY_NOTICES.md"
copy_file "LICENSE"

copy_tree "examples"
copy_tree ".github"
copy_tree "agents"
copy_tree "patches"
copy_tree "references"
copy_tree "scripts"
copy_tree "src"
copy_tree "tests"

rm -rf "$OUTPUT_DIR/dist"
chmod +x "$OUTPUT_DIR"/scripts/*.sh "$OUTPUT_DIR"/scripts/*.py

"$OUTPUT_DIR/scripts/audit_release.sh" "$OUTPUT_DIR"

printf 'Release directory created: %s\n' "$OUTPUT_DIR"
