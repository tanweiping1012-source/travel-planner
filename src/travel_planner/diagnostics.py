"""Local capability diagnostics without exposing credentials or account state."""

from __future__ import annotations

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


def build_doctor_report(
    amap_status: dict,
    *,
    data_dir: Optional[Path] = None,
    browser_status: str = "unknown",
    client: str = "codex",
    command_finder: Callable[[str], Optional[str]] = shutil.which,
    command_runner=subprocess.run,
) -> dict:
    resolved_data_dir = data_dir or default_data_dir()
    python_ready = sys.version_info >= (3, 9)
    rail_runtime = _rail_runtime_status(resolved_data_dir)
    rail_registration = (
        _codex_mcp_status(command_finder, command_runner)
        if client == "codex"
        else {
            "status": "UNVERIFIED",
            "message": "Verify the stdio MCP in the selected Agent client.",
        }
    )

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
        actions.append("Register the installed 12306 stdio MCP in Codex.")
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
        "rail_mcp": {
            "status": rail_status,
            "runtime": rail_runtime,
            "registration": rail_registration,
        },
        "browser": browser,
        "actions": actions,
    }
