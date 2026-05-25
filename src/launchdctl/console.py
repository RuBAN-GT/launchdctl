"""Terminal output with rich tables and ANSI fallback."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import Any


class Console:
    """Colored terminal output with optional rich tables."""

    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose
        self._rich_console: Any = None
        self._use_rich = False
        try:
            from rich.console import Console as RichConsole

            self._rich_console = RichConsole(stderr=False)
            self._use_rich = True
        except ImportError:
            pass

    def _ansi(self, text: str, code: str) -> str:
        if self._use_rich:
            return text
        return f"\033[{code}m{text}\033[0m"

    def info(self, msg: str) -> None:
        print(msg)

    def success(self, msg: str) -> None:
        if self._use_rich:
            self._rich_console.print(f"[green]✓[/green] {msg}")
        else:
            print(self._ansi(f"✓ {msg}", "32"))

    def warning(self, msg: str) -> None:
        if self._use_rich:
            self._rich_console.print(f"[yellow]⚠[/yellow] {msg}")
        else:
            print(self._ansi(f"⚠ {msg}", "33"), file=sys.stderr)

    def error(self, msg: str) -> None:
        if self._use_rich:
            self._rich_console.print(f"[red]✗[/red] {msg}", style="red")
        else:
            print(self._ansi(f"✗ {msg}", "31"), file=sys.stderr)

    def debug(self, msg: str) -> None:
        if self.verbose:
            if self._use_rich:
                self._rich_console.print(f"[dim]{msg}[/dim]")
            else:
                print(self._ansi(msg, "2"))

    def heading(self, msg: str) -> None:
        if self._use_rich:
            self._rich_console.print(f"\n[bold]{msg}[/bold]")
        else:
            print(f"\n{msg}")

    def print_table(
        self,
        title: str,
        columns: Sequence[str],
        rows: Sequence[Sequence[str]],
    ) -> None:
        if not rows:
            self.info(f"{title}: (empty)")
            return

        if self._use_rich:
            from rich.table import Table

            table = Table(title=title, show_header=True, header_style="bold")
            for col in columns:
                table.add_column(col)
            for row in rows:
                table.add_row(*row)
            self._rich_console.print(table)
            return

        widths = [
            max(len(col), max((len(r[i]) for r in rows), default=0))
            for i, col in enumerate(columns)
        ]
        self.heading(title)
        header = "  ".join(col.ljust(widths[i]) for i, col in enumerate(columns))
        print(header)
        print("  ".join("-" * w for w in widths))
        for row in rows:
            print("  ".join(row[i].ljust(widths[i]) for i in range(len(columns))))
