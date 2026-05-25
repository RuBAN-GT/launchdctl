"""Core launchd daemon management logic."""

from __future__ import annotations

import datetime
import difflib
import json
import plistlib
import shutil
import subprocess
import tempfile
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from launchdctl.__version__ import __version__
from launchdctl.config import DEFAULT_DUMP_KEYS, META_KEY, Config
from launchdctl.console import Console
from launchdctl.exceptions import CommandError, LaunchdCTLError
from launchdctl.models import DaemonStatus, SetupChange
from launchdctl.utils import (
    confirm,
    normalize_for_compare,
    run_cmd,
    strip_meta,
    to_yaml,
)


class LaunchdCTL:
    """Main controller for managed launchd daemons."""

    def __init__(self, console: Console, config: Config | None = None) -> None:
        self.console = console
        self.config = config or Config.load()

    def require_yq(self) -> str:
        """Ensure yq is available and return its path."""
        path = shutil.which("yq")
        if not path:
            raise LaunchdCTLError("yq is required. Install with: brew install yq")
        return path

    def load_plist(self, path: Path) -> dict[str, Any]:
        """Load a plist file via plutil (handles binary/XML)."""
        result = run_cmd(["plutil", "-convert", "xml1", "-o", "-", str(path)])
        data = plistlib.loads(result.stdout.encode("utf-8"))
        if not isinstance(data, dict):
            raise LaunchdCTLError(f"Invalid plist (not a dict): {path}")
        return data

    def load_yaml_as_dict(self, path: Path) -> dict[str, Any]:
        """Load YAML via yq and parse as JSON-compatible dict."""
        self.require_yq()
        result = run_cmd(["yq", "eval", "-o=json", str(path)])
        data = json.loads(result.stdout)
        if not isinstance(data, dict):
            raise LaunchdCTLError(f"YAML must be an object: {path}")
        return data

    def yaml_to_plist_file(self, yaml_path: Path, plist_path: Path) -> None:
        """Convert YAML to plist using yq + plutil."""
        self.require_yq()
        json_result = run_cmd(["yq", "eval", "-o=json", str(yaml_path)])
        data = json.loads(json_result.stdout)
        if not isinstance(data, dict):
            raise LaunchdCTLError(f"YAML must be an object: {yaml_path}")

        payload = strip_meta(data)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(payload, tmp)
            tmp_path = Path(tmp.name)

        try:
            plist_path.parent.mkdir(parents=True, exist_ok=True)
            run_cmd(
                ["plutil", "-convert", "xml1", "-o", str(plist_path), str(tmp_path)],
            )
        finally:
            tmp_path.unlink(missing_ok=True)

    def ensure_dirs(self) -> None:
        """Create YAML storage directories if missing."""
        for directory in self.config.yaml_dirs:
            directory.mkdir(parents=True, exist_ok=True)
        self.console.debug(
            f"Directories: {', '.join(str(path) for path in self.config.yaml_dirs)}",
        )

    def _yaml_exists(self, label: str) -> bool:
        for directory in self.config.yaml_dirs:
            if (directory / f"{label}.yaml").exists():
                return True
        return False

    def discover_plist_labels(self) -> list[str]:
        """Return sorted labels from installed plist files."""
        directory = self.config.launch_daemons_dir
        if not directory.is_dir():
            return []
        return sorted(path.stem for path in directory.glob("*.plist"))

    def list_managed_labels_from_launchctl(self) -> list[str]:
        """Return sorted managed labels from launchctl, YAML, and/or plists."""
        labels: set[str] = set()

        result = run_cmd(["launchctl", "list"], check=False)
        for line in result.stdout.strip().splitlines()[1:]:
            parts = [part.strip() for part in line.split("\t") if part.strip()]
            if len(parts) < 3:
                continue
            label = parts[2]
            if self.config.is_prefix_managed_label(label) or self._yaml_exists(label):
                labels.add(label)

        if not self.config.prefix_namespaces:
            labels.update(self.discover_plist_labels())
        elif self.config.default_namespace is not None:
            for label in self.discover_plist_labels():
                if not self.config.is_prefix_managed_label(label):
                    labels.add(label)

        return sorted(labels)

    def discover_yaml_labels(self) -> list[str]:
        """Return sorted labels from YAML files on disk."""
        labels: list[str] = []
        for directory in self.config.yaml_dirs:
            if not directory.is_dir():
                continue
            labels.extend(path.stem for path in sorted(directory.glob("*.yaml")))
        return sorted(set(labels))

    def filter_labels(
        self,
        labels: Iterable[str],
        *,
        namespaces: Sequence[str] | None = None,
    ) -> list[str]:
        """Filter label list by namespace name."""
        selected_namespaces = list(namespaces or [])

        result = list(labels)
        if not selected_namespaces:
            return sorted(result)

        allowed: set[str] = set()
        for namespace_name in selected_namespaces:
            namespace = self.config.namespace_by_name(namespace_name)
            if namespace is None:
                raise LaunchdCTLError(f"Unknown namespace: {namespace_name}")
            allowed.update(
                label
                for label in result
                if self.config.namespace_for_label(label).name == namespace.name
            )
        return sorted(label for label in result if label in allowed)

    def get_status(self, label: str) -> DaemonStatus:
        """Query runtime status for one daemon."""
        if not self.config.is_managed_label(label):
            raise LaunchdCTLError(
                f"Label is not in a managed namespace "
                f"({self.config.managed_namespace_hint()}): {label}",
            )

        disabled = self.is_disabled(label)
        result = run_cmd(["launchctl", "list"], check=False)
        pid: int | None = None
        exit_code: int | None = None

        for line in result.stdout.strip().splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            pid_raw, status_raw, line_label = (
                parts[0].strip(),
                parts[1].strip(),
                parts[2].strip(),
            )
            if line_label != label:
                continue
            if pid_raw != "-":
                try:
                    pid = int(pid_raw)
                except ValueError:
                    pid = None
            try:
                exit_code = int(status_raw)
            except ValueError:
                exit_code = None
            break

        if disabled:
            state = "disabled"
        elif pid and pid > 0:
            state = "running"
        else:
            state = "stopped"

        return DaemonStatus(
            label=label,
            pid=pid if pid and pid > 0 else None,
            last_exit_code=exit_code,
            state=state,
            disabled=disabled,
        )

    def is_disabled(self, label: str) -> bool:
        """Check whether daemon is disabled in launchd."""
        result = run_cmd(["launchctl", "print-disabled", "system"], check=False)
        if result.returncode != 0:
            self.console.debug(
                f"launchctl print-disabled unavailable: {result.stderr.strip()}",
            )
            return False
        return f'"{label}" => disabled' in result.stdout or f"{label} => disabled" in result.stdout

    def bootout(self, label: str) -> None:
        """Unload daemon from launchd."""
        target = self.config.launchd_target(label)
        result = run_cmd(["launchctl", "bootout", target], check=False)
        if result.returncode != 0 and "No such process" not in (result.stderr or ""):
            self.console.debug(f"bootout {target}: {result.stderr.strip()}")

    def bootstrap(self, label: str, plist_path: Path) -> None:
        """Load daemon into launchd."""
        run_cmd(["launchctl", "bootstrap", "system", str(plist_path)])

    def reload(self, label: str, plist_path: Path) -> None:
        """Reload daemon via bootout + bootstrap."""
        self.bootout(label)
        self.bootstrap(label, plist_path)

    def enable(self, label: str) -> None:
        """Enable daemon in launchd."""
        run_cmd(["launchctl", "enable", self.config.launchd_target(label)])

    def disable(self, label: str) -> None:
        """Disable daemon in launchd."""
        run_cmd(["launchctl", "disable", self.config.launchd_target(label)])

    def validate_yaml_file(self, path: Path) -> list[str]:
        """Validate one YAML daemon config; return list of error messages."""
        errors: list[str] = []
        label = path.stem

        if not self.config.is_managed_label(label):
            errors.append(
                f"{path.name}: label must start with {self.config.managed_namespace_hint()}.",
            )

        try:
            data = self.load_yaml_as_dict(path)
        except (CommandError, json.JSONDecodeError, LaunchdCTLError) as exc:
            errors.append(f"{path.name}: failed to read YAML — {exc}")
            return errors

        payload = strip_meta(data)
        file_label = payload.get("Label")
        if not file_label:
            errors.append(f"{path.name}: missing required key Label")
        elif file_label != label:
            errors.append(
                f"{path.name}: Label ({file_label}) does not match filename ({label})",
            )

        if not payload.get("Program") and not payload.get("ProgramArguments"):
            errors.append(f"{path.name}: Program or ProgramArguments is required")

        return errors

    def validate_all(self) -> tuple[list[Path], list[str]]:
        """Validate all YAML configs; return (valid_paths, all_errors)."""
        paths = [
            path
            for directory in self.config.yaml_dirs
            if directory.is_dir()
            for path in sorted(directory.glob("*.yaml"))
        ]
        all_errors: list[str] = []
        valid: list[Path] = []
        for path in paths:
            file_errors = self.validate_yaml_file(path)
            if file_errors:
                all_errors.extend(file_errors)
            else:
                valid.append(path)
        return valid, all_errors

    def diff_label(self, label: str) -> tuple[list[str], bool]:
        """Compare installed plist with YAML-derived config."""
        yaml_path = self.config.yaml_path_for_label(label)
        plist_path = self.config.plist_path_for_label(label)

        if not yaml_path.exists():
            raise LaunchdCTLError(f"YAML not found: {yaml_path}")

        desired = normalize_for_compare(self.load_yaml_as_dict(yaml_path))
        desired_yaml = to_yaml(desired) + "\n"

        if plist_path.exists():
            current = normalize_for_compare(self.load_plist(plist_path))
            current_yaml = to_yaml(current) + "\n"
        else:
            current_yaml = ""
            current = {}

        if current == desired:
            return [], False

        diff_lines = list(
            difflib.unified_diff(
                current_yaml.splitlines(keepends=True),
                desired_yaml.splitlines(keepends=True),
                fromfile=f"plist:{plist_path}",
                tofile=f"yaml:{yaml_path}",
            ),
        )
        return diff_lines, True

    def plan_setup_change(self, label: str) -> SetupChange:
        """Compute setup action for one label."""
        yaml_path = self.config.yaml_path_for_label(label)
        plist_path = self.config.plist_path_for_label(label)

        if not yaml_path.exists():
            return SetupChange(
                label=label,
                action="error",
                yaml_path=yaml_path,
                plist_path=plist_path,
                error=f"YAML not found: {yaml_path}",
            )

        file_errors = self.validate_yaml_file(yaml_path)
        if file_errors:
            return SetupChange(
                label=label,
                action="error",
                yaml_path=yaml_path,
                plist_path=plist_path,
                error="; ".join(file_errors),
            )

        diff_lines, has_changes = self.diff_label(label)
        if not plist_path.exists():
            action = "create"
        elif has_changes:
            action = "update"
        else:
            action = "unchanged"

        return SetupChange(
            label=label,
            action=action,
            yaml_path=yaml_path,
            plist_path=plist_path,
            diff_lines=diff_lines,
        )

    def cmd_dump(
        self,
        labels: Sequence[str],
        *,
        full: bool = False,
        namespaces: Sequence[str] | None = None,
    ) -> int:
        """Dump running plists to YAML files."""
        self.ensure_dirs()

        if labels:
            selected = self.filter_labels(labels)
        else:
            selected = self.filter_labels(
                self.list_managed_labels_from_launchctl(),
                namespaces=namespaces,
            )

        keys: tuple[str, ...] | None = None if full else DEFAULT_DUMP_KEYS
        self.console.info(f"Dumping {len(selected)} daemon(s)...")
        failed: list[str] = []

        for label in selected:
            plist_path = self.config.plist_path_for_label(label)
            if not plist_path.exists():
                self.console.warning(f"No plist: {label}")
                continue
            try:
                data = self.load_plist(plist_path)
                if keys:
                    data = {key: data[key] for key in keys if key in data}
                data[META_KEY] = {
                    "dumped_at": datetime.datetime.now().isoformat(timespec="seconds"),
                    "source_plist": str(plist_path),
                    "tool": f"launchdctl v{__version__}",
                }
                out_path = self.config.yaml_path_for_label(label)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(to_yaml(data) + "\n")
                self.console.success(label)
            except LaunchdCTLError as exc:
                self.console.error(f"{label}: {exc}")
                failed.append(label)

        if failed:
            self.console.error(f"Failed to process: {', '.join(failed)}")
            return 1

        self._fix_yaml_permissions()
        self.console.info(
            f"\nDone. YAML files: {', '.join(str(path) for path in self.config.yaml_dirs)}",
        )
        return 0

    def cmd_setup(
        self,
        labels: Sequence[str],
        *,
        dry_run: bool = False,
        force: bool = False,
        namespaces: Sequence[str] | None = None,
    ) -> int:
        """Apply YAML configs to installed plists and reload daemons."""
        self.require_yq()
        self.ensure_dirs()

        if labels:
            selected = self.filter_labels(labels)
        else:
            selected = self.filter_labels(
                self.discover_yaml_labels(),
                namespaces=namespaces,
            )

        if not selected:
            self.console.warning("No daemons to set up.")
            return 0

        plans = [self.plan_setup_change(label) for label in selected]
        errors = [plan for plan in plans if plan.action == "error"]
        actionable = [plan for plan in plans if plan.action in {"create", "update"}]

        for plan in plans:
            if plan.action == "error":
                self.console.error(f"{plan.label}: {plan.error}")
            elif plan.action == "unchanged":
                self.console.info(f"  = {plan.label} (unchanged)")
            elif dry_run:
                action_label = "CREATE" if plan.action == "create" else "UPDATE"
                self.console.heading(f"{action_label}: {plan.label}")
                if plan.diff_lines:
                    print("".join(plan.diff_lines))
            else:
                self.console.info(f"  ~ {plan.label} ({plan.action})")

        if errors:
            return 1

        if not actionable:
            self.console.success("No changes.")
            return 0

        if dry_run:
            self.console.info(
                f"\n[dry-run] Would change {len(actionable)} daemon(s).",
            )
            return 0

        if len(actionable) > 1 and not force:
            if not confirm(f"Apply changes to {len(actionable)} daemon(s)?"):
                self.console.warning("Cancelled.")
                return 1

        self.console.heading("Applying changes")
        reloaded: list[str] = []
        setup_failed: list[str] = []

        for plan in actionable:
            try:
                self.console.debug(f"Converting {plan.yaml_path} → {plan.plist_path}")
                self.yaml_to_plist_file(plan.yaml_path, plan.plist_path)
                self.reload(plan.label, plan.plist_path)
                plan.reloaded = True
                reloaded.append(plan.label)
                self.console.success(f"{plan.label} — plist updated and reloaded")
            except (CommandError, LaunchdCTLError, OSError) as exc:
                plan.error = str(exc)
                setup_failed.append(plan.label)
                self.console.error(f"{plan.label}: {exc}")

        self.console.heading("Setup summary")
        if reloaded:
            self.console.info(f"Reloaded ({len(reloaded)}): {', '.join(reloaded)}")
        if setup_failed:
            self.console.error(f"Errors ({len(setup_failed)}): {', '.join(setup_failed)}")
            return 1

        self.console.success("Setup complete.")
        return 0

    def cmd_list(self) -> int:
        """List managed daemons grouped by namespace."""
        labels = self.list_managed_labels_from_launchctl()
        for namespace in self.config.namespaces:
            namespace_labels = self.config.labels_for_namespace(namespace.name, labels)
            rows: list[list[str]] = []
            for label in namespace_labels:
                status = self.get_status(label)
                rows.append([label, status.state, str(status.pid or "-")])
            self.console.print_table(
                namespace.display_title,
                ["Label", "State", "PID"],
                rows,
            )
        return 0

    def cmd_status(self, label: str | None) -> int:
        """Show runtime status for one or all managed daemons."""
        if label:
            if not self.config.is_managed_label(label):
                self.console.error(
                    f"Label is not in a managed namespace "
                    f"({self.config.managed_namespace_hint()}): {label}",
                )
                return 1
            labels = [label]
        else:
            labels = self.list_managed_labels_from_launchctl()

        rows: list[list[str]] = []
        for item in labels:
            status = self.get_status(item)
            rows.append(
                [
                    item,
                    status.state,
                    str(status.pid or "-"),
                    str(
                        status.last_exit_code if status.last_exit_code is not None else "-",
                    ),
                    "yes" if status.disabled else "no",
                ],
            )

        self.console.print_table(
            "Daemon status",
            ["Label", "State", "PID", "LastExit", "Disabled"],
            rows,
        )
        return 0

    def cmd_show(self, label: str) -> int:
        """Print YAML config for a daemon."""
        path = self.config.yaml_path_for_label(label)
        if not path.exists():
            self.console.error(f"YAML for {label} not found. Run dump first.")
            return 1
        print(path.read_text())
        return 0

    def cmd_diff(self, label: str) -> int:
        """Show diff between installed plist and YAML config."""
        try:
            diff_lines, has_changes = self.diff_label(label)
        except LaunchdCTLError as exc:
            self.console.error(str(exc))
            return 1

        if not has_changes:
            self.console.success(f"{label}: plist matches YAML")
            return 0

        print("".join(diff_lines))
        return 0

    def cmd_validate(self) -> int:
        """Validate all YAML daemon configs."""
        valid, errors = self.validate_all()
        for err in errors:
            self.console.error(err)

        if errors:
            self.console.error(f"Errors: {len(errors)}, valid: {len(valid)}")
            return 1

        self.console.success(f"All {len(valid)} YAML file(s) are valid.")
        return 0

    def cmd_enable(self, label: str) -> int:
        """Enable a managed daemon."""
        if not self.config.is_managed_label(label):
            self.console.error(
                f"Label is not in a managed namespace "
                f"({self.config.managed_namespace_hint()}): {label}",
            )
            return 1
        try:
            self.enable(label)
            self.console.success(f"{label} enabled")
        except CommandError as exc:
            self.console.error(str(exc))
            return 1
        return 0

    def cmd_disable(self, label: str) -> int:
        """Disable a managed daemon."""
        if not self.config.is_managed_label(label):
            self.console.error(
                f"Label is not in a managed namespace "
                f"({self.config.managed_namespace_hint()}): {label}",
            )
            return 1
        try:
            self.disable(label)
            self.console.success(f"{label} disabled")
        except CommandError as exc:
            self.console.error(str(exc))
            return 1
        return 0

    def _fix_yaml_permissions(self) -> None:
        """Fix ownership and permissions on YAML directories (best-effort)."""
        for namespace in self.config.namespaces:
            if namespace.chown:
                subprocess.run(
                    ["sudo", "chown", "-R", namespace.chown, str(namespace.yaml_dir)],
                    check=False,
                )
        dirs = [str(path) for path in self.config.yaml_dirs]
        if dirs:
            mode = format(self.config.yaml_dir_mode, "o")
            subprocess.run(
                ["sudo", "chmod", "-R", mode, *dirs],
                check=False,
            )
