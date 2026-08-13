#!/usr/bin/env python3
"""Validate the repository's Agent Skill metadata and UI declaration."""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ALLOWED_FRONTMATTER_KEYS = {"name", "description"}


def _parse_scalar(value: str, path: Path) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{path} contains an empty YAML value")
    if value[0] in {"'", '"'}:
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError) as exc:
            raise ValueError(f"Unable to parse a quoted value in {path}") from exc
        if not isinstance(parsed, str):
            raise ValueError(f"{path} metadata values must be strings")
        return parsed
    return value


def _parse_mapping(lines: list[str], path: Path, indent: int = 0) -> dict:
    data = {}
    prefix = " " * indent
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(prefix) or line[indent:].startswith(" "):
            raise ValueError(f"Unexpected indentation in {path}: {line!r}")
        if ":" not in line:
            raise ValueError(f"Expected key: value metadata in {path}: {line!r}")
        key, value = line[indent:].split(":", 1)
        key = key.strip()
        if not key or key in data:
            raise ValueError(f"Invalid or duplicate key in {path}: {key!r}")
        data[key] = _parse_scalar(value, path)
    return data


def _load_agent_metadata(path: Path) -> dict:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"Unable to read {path}: {exc}") from exc
    significant = [line for line in lines if line.strip() and not line.lstrip().startswith("#")]
    if not significant or significant[0].strip() != "interface:":
        raise ValueError(f"{path} must start with an interface mapping")
    return {"interface": _parse_mapping(significant[1:], path, indent=2)}


def _load_frontmatter(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Unable to read {path}: {exc}") from exc
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{path} must start with YAML frontmatter")
    try:
        closing_index = next(
            index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"
        )
    except StopIteration as exc:
        raise ValueError(f"{path} frontmatter is not closed") from exc
    return _parse_mapping(lines[1:closing_index], path)


def validate_skill(root: Path) -> list[str]:
    errors = []
    skill_path = root / "SKILL.md"
    agent_path = root / "agents" / "openai.yaml"

    try:
        frontmatter = _load_frontmatter(skill_path)
    except ValueError as exc:
        return [str(exc)]

    unknown_keys = sorted(set(frontmatter) - ALLOWED_FRONTMATTER_KEYS)
    if unknown_keys:
        errors.append(f"SKILL.md contains unsupported frontmatter keys: {unknown_keys}")

    name = frontmatter.get("name")
    if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name):
        errors.append("SKILL.md name must use lowercase letters, digits, and single hyphens")
    elif len(name) > 64:
        errors.append("SKILL.md name must be at most 64 characters")

    description = frontmatter.get("description")
    if not isinstance(description, str) or not description.strip():
        errors.append("SKILL.md description must be a non-empty string")
    elif len(description) > 1024:
        errors.append("SKILL.md description must be at most 1024 characters")

    if not agent_path.is_file():
        errors.append("agents/openai.yaml is missing")
        return errors

    try:
        agent_data = _load_agent_metadata(agent_path)
    except ValueError as exc:
        errors.append(str(exc))
        return errors

    interface = agent_data.get("interface")
    if not isinstance(interface, dict):
        errors.append("agents/openai.yaml must contain an interface mapping")
        return errors

    display_name = interface.get("display_name")
    if not isinstance(display_name, str) or not display_name.strip():
        errors.append("interface.display_name must be a non-empty string")

    short_description = interface.get("short_description")
    if not isinstance(short_description, str):
        errors.append("interface.short_description must be a string")
    elif not 25 <= len(short_description) <= 64:
        errors.append("interface.short_description must be 25-64 characters")

    default_prompt = interface.get("default_prompt")
    expected_reference = f"${name}" if isinstance(name, str) else None
    if not isinstance(default_prompt, str) or not default_prompt.strip():
        errors.append("interface.default_prompt must be a non-empty string")
    elif expected_reference and expected_reference not in default_prompt:
        errors.append(f"interface.default_prompt must reference {expected_reference}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    errors = validate_skill(root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Skill validation passed: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
