"""Data models for daemon state and setup planning."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DaemonStatus:
    """Runtime status of a launchd job."""

    label: str
    pid: int | None
    last_exit_code: int | None
    state: str
    disabled: bool = False

    @property
    def running(self) -> bool:
        return self.pid is not None and self.pid > 0


@dataclass
class SetupChange:
    """Planned or applied setup change for one daemon."""

    label: str
    action: str  # create | update | unchanged | error
    yaml_path: Path
    plist_path: Path
    reloaded: bool = False
    error: str | None = None
    diff_lines: list[str] = field(default_factory=list)
