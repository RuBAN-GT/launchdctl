"""Shared helpers for subprocess, serialization, and user prompts."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Sequence
from typing import Any

from launchdctl.config import META_KEY
from launchdctl.exceptions import CommandError


def run_cmd(
    cmd: Sequence[str],
    *,
    input_text: str | None = None,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess command with consistent error handling."""
    result = subprocess.run(
        list(cmd),
        input=input_text,
        capture_output=capture,
        text=True,
    )
    if check and result.returncode != 0:
        raise CommandError(cmd, result.stderr or result.stdout or "", result.returncode)
    return result


def to_yaml(obj: Any, level: int = 0) -> str:
    """Serialize Python objects to a readable YAML-like string."""
    indent = "  " * level
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        lines: list[str] = []
        for key in sorted(obj.keys()):
            value = obj[key]
            if isinstance(value, (dict, list)) and value:
                lines.append(f"{indent}{key}:")
                lines.append(to_yaml(value, level + 1))
            else:
                rendered = to_yaml(value, level + 1).lstrip()
                lines.append(f"{indent}{key}: {rendered}")
        return "\n".join(lines)
    if isinstance(obj, list):
        if not obj:
            return "[]"
        return "\n".join(f"{indent}- {to_yaml(item, level + 1).lstrip()}" for item in obj)
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, (int, float)):
        return str(obj)
    if isinstance(obj, str):
        if any(ch in obj for ch in "\n:#\"'  ") or not obj:
            escaped = obj.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        return obj
    if obj is None:
        return "null"
    return str(obj)


def strip_meta(data: dict[str, Any]) -> dict[str, Any]:
    """Remove _meta block from daemon config dict."""
    return {k: v for k, v in data.items() if k != META_KEY}


def normalize_for_compare(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize plist/YAML dict for structural comparison."""
    cleaned = strip_meta(data)
    return json.loads(json.dumps(cleaned, sort_keys=True, default=str))


def confirm(prompt: str) -> bool:
    """Ask user for yes/no confirmation."""
    try:
        answer = input(f"{prompt} [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print(file=sys.stderr)
        return False
    return answer in {"y", "yes"}
