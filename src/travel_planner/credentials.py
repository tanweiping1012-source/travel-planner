"""Credential access that keeps provider secrets outside prompts and source code."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


class CredentialError(RuntimeError):
    """Raised when a provider credential cannot be loaded."""


@dataclass(frozen=True)
class CredentialSpec:
    service: str
    account: str
    environment_variable: str


PROVIDERS = {
    "amap": CredentialSpec(
        service="trae-travel-planner",
        account="amap-api-key",
        environment_variable="AMAP_API_KEY",
    ),
}


class KeychainCredentialStore:
    """Load credentials from macOS Keychain, with an environment override for CI."""

    def get(self, provider: str) -> str:
        try:
            spec = PROVIDERS[provider]
        except KeyError as exc:
            raise CredentialError(f"Unsupported credential provider: {provider}") from exc

        environment_value = os.environ.get(spec.environment_variable, "").strip()
        if environment_value:
            return environment_value

        try:
            result = subprocess.run(
                [
                    "security",
                    "find-generic-password",
                    "-s",
                    spec.service,
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
        except subprocess.CalledProcessError as exc:
            raise CredentialError(
                "Amap API key is not configured in macOS Keychain"
            ) from exc

        value = result.stdout.strip()
        if not value:
            raise CredentialError("Amap API key in macOS Keychain is empty")
        return value

    def status(self, provider: str) -> dict:
        try:
            self.get(provider)
        except CredentialError as exc:
            return {"provider": provider, "status": "MISSING", "message": str(exc)}
        return {"provider": provider, "status": "CONFIGURED"}
