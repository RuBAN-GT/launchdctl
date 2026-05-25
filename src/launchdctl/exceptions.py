"""Custom exceptions for launchdctl."""

from __future__ import annotations

from collections.abc import Sequence


class LaunchdCTLError(Exception):
    """Base error for launchdctl operations."""


class CommandError(LaunchdCTLError):
    """External command failed."""

    def __init__(self, cmd: Sequence[str], stderr: str, code: int) -> None:
        self.cmd = list(cmd)
        self.stderr = stderr.strip()
        self.code = code
        super().__init__(
            f"{' '.join(self.cmd)} failed (exit {code}): {self.stderr}",
        )


class ValidationError(LaunchdCTLError):
    """YAML or plist validation failed."""
