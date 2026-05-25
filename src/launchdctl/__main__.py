"""Allow running as python -m launchdctl."""

from launchdctl.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
