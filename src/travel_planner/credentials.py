"""Credential access that keeps provider secrets outside prompts and source code."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence


class CredentialError(RuntimeError):
    """Raised when a provider credential cannot be loaded."""


@dataclass(frozen=True)
class CredentialSpec:
    service: str
    account: str
    environment_variable: str
    legacy_services: Sequence[str] = ()


PROVIDERS = {
    "amap": CredentialSpec(
        service="travel-planner-mvp",
        account="amap-api-key",
        environment_variable="AMAP_API_KEY",
        legacy_services=("trae-travel-planner",),
    ),
}


class KeychainCredentialStore:
    """Load credentials from macOS Keychain, with an environment override for CI."""

    def __init__(
        self,
        environment: Optional[Mapping[str, str]] = None,
        command_runner=None,
    ):
        self._environment = environment if environment is not None else os.environ
        self._command_runner = command_runner or subprocess.run

    def get_with_source(self, provider: str) -> tuple[str, str]:
        try:
            spec = PROVIDERS[provider]
        except KeyError as exc:
            raise CredentialError(f"Unsupported credential provider: {provider}") from exc

        environment_value = self._environment.get(spec.environment_variable, "").strip()
        if environment_value:
            return environment_value, "environment"

        for index, service in enumerate((spec.service, *spec.legacy_services)):
            try:
                result = self._command_runner(
                    [
                        "security",
                        "find-generic-password",
                        "-s",
                        service,
                        "-a",
                        spec.account,
                        "-w",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except FileNotFoundError as exc:
                raise CredentialError("macOS Keychain command is unavailable") from exc
            except subprocess.CalledProcessError:
                continue

            value = result.stdout.strip()
            if not value:
                continue
            source = "macos-keychain" if index == 0 else "macos-keychain-legacy"
            return value, source

        raise CredentialError("Amap API key is not configured")

    def get(self, provider: str) -> str:
        value, _source = self.get_with_source(provider)
        return value

    def status(self, provider: str) -> dict:
        try:
            _value, source = self.get_with_source(provider)
        except CredentialError as exc:
            return {"provider": provider, "status": "MISSING", "message": str(exc)}
        return {"provider": provider, "status": "CONFIGURED", "source": source}
