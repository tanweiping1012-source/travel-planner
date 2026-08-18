"""Local capability diagnostics without exposing credentials or account state."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Mapping, Optional


def default_data_dir(
    environment: Optional[Mapping[str, str]] = None,
    system_name: Optional[str] = None,
    home: Optional[Path] = None,
) -> Path:
    environment = environment if environment is not None else os.environ
    configured = environment.get("TRAVEL_PLANNER_DATA_DIR", "").strip()
    if configured:
        configured_path = Path(configured).expanduser()
        if not configured_path.is_absolute():
            raise ValueError("TRAVEL_PLANNER_DATA_DIR must be an absolute path")
        return configured_path.resolve()

    user_home = home or Path.home()
    current_system = system_name or platform.system()
    if current_system == "Darwin":
        return user_home / "Library" / "Application Support" / "travel-planner-mvp"

    xdg_data_home = environment.get("XDG_DATA_HOME", "").strip()
    base = Path(xdg_data_home).expanduser() if xdg_data_home else user_home / ".local" / "share"
    return base / "travel-planner-mvp"


def _rail_runtime_status(data_dir: Path) -> dict:
    checkout = data_dir / "mcp-server-12306"
    ready = (checkout / "pyproject.toml").is_file() and (checkout / ".venv").is_dir()
    return {
        "status": "READY" if ready else "MISSING",
        "path": str(checkout),
    }


def _codex_mcp_status(
    command_finder: Callable[[str], Optional[str]],
    command_runner,
) -> dict:
    codex = command_finder("codex")
    if not codex:
        return {
            "status": "UNAVAILABLE",
            "message": "Codex CLI is unavailable; verify MCP registration in the client settings.",
        }

    result = command_runner(
        [codex, "mcp", "get", "12306"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return {"status": "READY"}
    return {
        "status": "MISSING",
        "message": "The 12306 MCP is not registered in Codex.",
    }


def _claude_code_mcp_status(
    server_name: str = "12306",
    config_path: Optional[Path] = None,
) -> dict:
    """Check whether Claude Code has the rail MCP registered.

    Only the presence of the server name is read. The rest of the file holds
    unrelated account and project state, none of which belongs in a report.
    """

    path = config_path or Path.home() / ".claude.json"
    if not path.is_file():
        return {
            "status": "MISSING",
            "message": "No Claude Code configuration found at ~/.claude.json.",
        }
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {
            "status": "UNVERIFIED",
            "message": "The Claude Code configuration could not be read.",
        }
    servers = config.get("mcpServers")
    if isinstance(servers, dict) and server_name in servers:
        return {"status": "READY", "client": "claude-code"}
    return {
        "status": "MISSING",
        "message": "The 12306 MCP is not registered in Claude Code.",
    }


def detect_client(
    environment: Optional[Mapping[str, str]] = None,
    command_finder: Callable[[str], Optional[str]] = shutil.which,
) -> str:
    """Guess which Agent client is running this Skill."""

    environment = environment if environment is not None else os.environ
    if environment.get("CLAUDECODE") or environment.get("CLAUDE_CODE_ENTRYPOINT"):
        return "claude-code"
    if environment.get("CODEX_SANDBOX") or environment.get("CODEX_HOME"):
        return "codex"
    if command_finder("codex"):
        return "codex"
    if (Path.home() / ".claude.json").is_file():
        return "claude-code"
    return "generic"


def build_doctor_report(
    amap_status: dict,
    *,
    data_dir: Optional[Path] = None,
    browser_status: str = "unknown",
    client: str = "auto",
    claude_config_path: Optional[Path] = None,
    command_finder: Callable[[str], Optional[str]] = shutil.which,
    command_runner=subprocess.run,
) -> dict:
    resolved_data_dir = data_dir or default_data_dir()
    python_ready = sys.version_info >= (3, 9)
    rail_runtime = _rail_runtime_status(resolved_data_dir)
    if client == "auto":
        client = detect_client(command_finder=command_finder)
    if client == "codex":
        rail_registration = _codex_mcp_status(command_finder, command_runner)
    elif client == "claude-code":
        rail_registration = _claude_code_mcp_status(config_path=claude_config_path)
    else:
        rail_registration = {
            "status": "UNVERIFIED",
            "message": "Verify the stdio MCP in the selected Agent client.",
        }

    if rail_runtime["status"] == "READY" and rail_registration["status"] == "READY":
        rail_status = "READY"
    elif rail_runtime["status"] == "MISSING":
        rail_status = "MISSING"
    else:
        rail_status = "PARTIAL"

    browser_map = {
        "available": {
            "status": "AVAILABLE",
            "message": "The Agent reported an interactive browser capability.",
        },
        "unavailable": {
            "status": "UNAVAILABLE",
            "message": "Browser-backed OTA and Xiaohongshu research will be skipped.",
        },
        "unknown": {
            "status": "UNVERIFIED",
            "message": "The CLI cannot inspect Agent browser tools; confirm in the client.",
        },
    }
    browser = browser_map[browser_status]

    actions = []
    if not python_ready:
        actions.append("Install Python 3.9 or newer.")
    if amap_status.get("status") not in {"CONFIGURED", "READY"}:
        actions.append("Configure an Amap Web Service API key.")
    if rail_runtime["status"] == "MISSING":
        actions.append(
            "Run setup_rail_mcp.sh from the installed Skill to install the rail runtime."
        )
    elif rail_registration["status"] == "MISSING":
        actions.append(
            "Register the installed 12306 stdio MCP in "
            + {"codex": "Codex", "claude-code": "Claude Code"}.get(client, "the client")
            + "."
        )
    if browser["status"] == "UNVERIFIED":
        actions.append("Confirm whether the Agent client provides an interactive browser.")

    core_ready = python_ready and amap_status.get("status") in {"CONFIGURED", "READY"}
    overall = "READY" if core_ready and rail_status == "READY" else "PARTIAL"
    if not core_ready:
        overall = "NOT_READY"

    return {
        "status": overall,
        "core": {
            "python": {
                "status": "READY" if python_ready else "UNSUPPORTED",
                "version": platform.python_version(),
            },
            "amap": amap_status,
        },
        "client": client,
        "rail_mcp": {
            "status": rail_status,
            "runtime": rail_runtime,
            "registration": rail_registration,
        },
        "browser": browser,
        "actions": actions,
    }
