"""Command-line interface for launchdctl."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path

from launchdctl.__version__ import __version__
from launchdctl.config import Config
from launchdctl.console import Console
from launchdctl.controller import LaunchdCTL
from launchdctl.exceptions import LaunchdCTLError


def build_parser() -> argparse.ArgumentParser:
    """Build argparse parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="launchdctl",
        description=f"Launch Daemon Controller v{__version__}",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="Path to YAML config (or set LAUNCHDCTL_CONFIG)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    def add_ns_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--namespace",
            action="append",
            default=[],
            metavar="NAME",
            help="Limit to configured namespace (repeatable)",
        )

    p = sub.add_parser("dump", help="Export plist to YAML")
    p.add_argument("labels", nargs="*", help="Specific labels")
    p.add_argument("--full", action="store_true", help="Dump all plist keys")
    add_ns_flags(p)

    p = sub.add_parser("setup", help="Apply YAML to plist and reload")
    p.add_argument("labels", nargs="*", help="Specific labels")
    p.add_argument("--dry-run", action="store_true", help="Show changes without applying")
    p.add_argument("--force", action="store_true", help="Skip confirmation when changing >1 daemon")
    add_ns_flags(p)

    sub.add_parser("list", help="List managed daemons")

    p = sub.add_parser("status", help="Daemon status (running/stopped, PID, exit code)")
    p.add_argument("label", nargs="?", help="Label (all if omitted)")

    p = sub.add_parser("show", help="Show YAML config")
    p.add_argument("label")

    p = sub.add_parser("diff", help="Compare plist with YAML")
    p.add_argument("label")

    sub.add_parser("validate", help="Validate all YAML configs")

    p = sub.add_parser("enable", help="Enable a daemon")
    p.add_argument("label")

    p = sub.add_parser("disable", help="Disable a daemon")
    p.add_argument("label")

    return parser


def dispatch(ctl: LaunchdCTL, args: argparse.Namespace) -> int:
    """Route parsed CLI args to controller methods."""
    handlers: dict[str, Callable[[argparse.Namespace], int]] = {
        "dump": lambda a: ctl.cmd_dump(
            a.labels,
            full=a.full,
            namespaces=a.namespace or None,
        ),
        "setup": lambda a: ctl.cmd_setup(
            a.labels,
            dry_run=a.dry_run,
            force=a.force,
            namespaces=a.namespace or None,
        ),
        "list": lambda a: ctl.cmd_list(),
        "status": lambda a: ctl.cmd_status(a.label),
        "show": lambda a: ctl.cmd_show(a.label),
        "diff": lambda a: ctl.cmd_diff(a.label),
        "validate": lambda a: ctl.cmd_validate(),
        "enable": lambda a: ctl.cmd_enable(a.label),
        "disable": lambda a: ctl.cmd_disable(a.label),
    }
    handler = handlers.get(args.command)
    if handler is None:
        raise LaunchdCTLError(f"Unknown command: {args.command}")
    return handler(args)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    console = Console(verbose=args.verbose)
    config_path = Path(args.config).expanduser() if args.config else None
    config = Config.load(config_path)
    ctl = LaunchdCTL(console, config)

    try:
        return dispatch(ctl, args)
    except LaunchdCTLError as exc:
        console.error(str(exc))
        return 1
    except KeyboardInterrupt:
        console.warning("\nInterrupted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
