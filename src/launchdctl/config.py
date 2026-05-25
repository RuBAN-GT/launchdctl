"""Configuration loaded from environment variables and optional config file."""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from launchdctl.exceptions import LaunchdCTLError

DEFAULT_LAUNCH_DAEMONS_DIR = Path("/Library/LaunchDaemons")
DEFAULT_YAML_DIR = Path.home() / ".local" / "share" / "launchdctl" / "daemons"
DEFAULT_YAML_DIR_MODE = 0o770

DEFAULT_DUMP_KEYS: tuple[str, ...] = (
    "Label",
    "Program",
    "ProgramArguments",
    "UserName",
    "GroupName",
    "RunAtLoad",
    "KeepAlive",
    "StandardOutPath",
    "StandardErrorPath",
    "WorkingDirectory",
    "EnvironmentVariables",
    "LimitLoadToSessionType",
    "ProcessType",
    "Nice",
    "ThrottleInterval",
    "ExitTimeOut",
)

META_KEY = "_meta"

_CONFIG_FILENAMES = ("config.yaml", "config.yml")


def _user_config_paths(home: Path) -> tuple[Path, ...]:
    config_root = home / ".config" / "launchdctl"
    return tuple(config_root / name for name in _CONFIG_FILENAMES)


def config_search_paths() -> tuple[Path, ...]:
    """Return config file paths in search order."""
    paths: list[Path] = [
        Path("/etc/launchdctl.yaml"),
        Path("/etc/launchdctl.yml"),
        *_user_config_paths(Path.home()),
    ]

    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user and sudo_user not in ("", "root"):
        try:
            import pwd

            sudo_home = Path(pwd.getpwnam(sudo_user).pw_dir)
        except (KeyError, ImportError):
            sudo_home = Path("/Users") / sudo_user
        if sudo_home != Path.home():
            paths.extend(_user_config_paths(sudo_home))

    return tuple(dict.fromkeys(paths))


def _env_optional(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return None
    return value.strip()


def _load_yaml_config(path: Path) -> dict[str, Any]:
    """Load optional YAML config file via yq (if available) or skip."""
    if not path.is_file():
        return {}

    try:
        import json
        import shutil
        import subprocess

        yq = shutil.which("yq")
        if not yq:
            return {}

        result = subprocess.run(
            [yq, "eval", "-o=json", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return {}

        data = json.loads(result.stdout)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _parse_chown(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_yaml_dir_mode(value: Any) -> int:
    if isinstance(value, str):
        text = value.strip().lower()
        return int(text, 8) if text.startswith("0o") else int(text)
    return int(value)


@dataclass(frozen=True)
class NamespaceMapping:
    """Maps launchd label prefixes to YAML storage locations."""

    name: str
    prefix: str
    yaml_dir: Path
    chown: str | None = None

    @property
    def is_default(self) -> bool:
        """True when this mapping catches labels without a prefix match."""
        return self.prefix == ""

    @property
    def display_title(self) -> str:
        if self.is_default:
            return f"{self.name} (default)"
        return f"{self.prefix}* [{self.name}]"


@dataclass(frozen=True)
class Config:
    """Runtime configuration for launchdctl."""

    namespaces: tuple[NamespaceMapping, ...]
    launch_daemons_dir: Path
    yaml_dir_mode: int = DEFAULT_YAML_DIR_MODE

    @property
    def prefix_namespaces(self) -> tuple[NamespaceMapping, ...]:
        return tuple(ns for ns in self.namespaces if not ns.is_default)

    @property
    def default_namespace(self) -> NamespaceMapping | None:
        for namespace in self.namespaces:
            if namespace.is_default:
                return namespace
        return None

    @property
    def managed_prefixes(self) -> tuple[str, ...]:
        return tuple(ns.prefix for ns in self.prefix_namespaces)

    @property
    def yaml_dirs(self) -> tuple[Path, ...]:
        return tuple(dict.fromkeys(ns.yaml_dir for ns in self.namespaces))

    @classmethod
    def load(cls, config_path: Path | None = None) -> Config:
        """
        Build config from env vars with optional YAML file overlay.

        Precedence: environment variables > config file > defaults.
        """
        file_data: dict[str, Any] = {}
        explicit = config_path or _env_optional("LAUNCHDCTL_CONFIG")
        search_paths: list[Path] = []
        if explicit:
            search_paths.append(Path(explicit).expanduser())
        search_paths.extend(config_search_paths())

        for path in search_paths:
            file_data = _load_yaml_config(path)
            if file_data:
                break

        def pick(key: str, env: str, default: Any) -> Any:
            if env in os.environ:
                return os.environ[env]
            if key in file_data and file_data[key] is not None:
                return file_data[key]
            return default

        launch_daemons_dir = Path(
            pick(
                "launch_daemons_dir",
                "LAUNCHDCTL_LAUNCH_DAEMONS_DIR",
                DEFAULT_LAUNCH_DAEMONS_DIR,
            ),
        ).expanduser()

        yaml_dir_mode = _parse_yaml_dir_mode(
            pick("yaml_dir_mode", "LAUNCHDCTL_YAML_DIR_MODE", DEFAULT_YAML_DIR_MODE),
        )

        namespaces = cls._load_namespaces(file_data, pick)
        return cls(
            namespaces=namespaces,
            launch_daemons_dir=launch_daemons_dir,
            yaml_dir_mode=yaml_dir_mode,
        )

    @classmethod
    def _load_namespaces(
        cls,
        file_data: dict[str, Any],
        pick: Any,
    ) -> tuple[NamespaceMapping, ...]:
        raw_namespaces = file_data.get("namespaces")
        if isinstance(raw_namespaces, list) and raw_namespaces:
            namespaces = [_namespace_from_dict(item) for item in raw_namespaces]
        else:
            yaml_dir = Path(
                pick("yaml_dir", "LAUNCHDCTL_YAML_DIR", DEFAULT_YAML_DIR),
            ).expanduser()
            namespaces = [
                NamespaceMapping(
                    name="default",
                    prefix="",
                    yaml_dir=yaml_dir,
                    chown=_parse_chown(pick("chown", "LAUNCHDCTL_CHOWN", None)),
                ),
            ]

        default_data = file_data.get("default")
        default_dir = pick("default_dir", "LAUNCHDCTL_DEFAULT_DIR", None)
        default_chown = pick("default_chown", "LAUNCHDCTL_DEFAULT_CHOWN", None)

        if isinstance(default_data, dict):
            default_dir = default_data.get("yaml_dir", default_dir)
            if "chown" in default_data:
                default_chown = default_data.get("chown")

        has_default = any(namespace.is_default for namespace in namespaces)
        if default_dir and not has_default:
            namespaces.append(
                NamespaceMapping(
                    name="default",
                    prefix="",
                    yaml_dir=Path(default_dir).expanduser(),
                    chown=_parse_chown(default_chown),
                ),
            )

        if not namespaces:
            raise LaunchdCTLError("At least one namespace mapping must be configured.")

        cls._validate_namespaces(namespaces)
        return tuple(namespaces)

    @staticmethod
    def _validate_namespaces(namespaces: list[NamespaceMapping]) -> None:
        names = [namespace.name for namespace in namespaces]
        if len(names) != len(set(names)):
            raise LaunchdCTLError("Namespace names must be unique.")

        defaults = [namespace for namespace in namespaces if namespace.is_default]
        if len(defaults) > 1:
            raise LaunchdCTLError("Only one default namespace is allowed.")

        prefixes = [namespace.prefix for namespace in namespaces if namespace.prefix]
        if len(prefixes) != len(set(prefixes)):
            raise LaunchdCTLError("Namespace prefixes must be unique.")

    def namespace_for_label(self, label: str) -> NamespaceMapping:
        """Resolve the namespace for a label using longest-prefix matching."""
        matched: list[NamespaceMapping] = [
            namespace for namespace in self.prefix_namespaces if label.startswith(namespace.prefix)
        ]
        if matched:
            return max(matched, key=lambda namespace: len(namespace.prefix))

        default = self.default_namespace
        if default is not None:
            return default

        raise LaunchdCTLError(
            f"No namespace mapping for label '{label}'. "
            f"Configured prefixes: {self.managed_namespace_hint()}.",
        )

    def namespace_by_name(self, name: str) -> NamespaceMapping | None:
        for namespace in self.namespaces:
            if namespace.name == name:
                return namespace
        return None

    def yaml_dir_for_label(self, label: str) -> Path:
        return self.namespace_for_label(label).yaml_dir

    def plist_path_for_label(self, label: str) -> Path:
        return self.launch_daemons_dir / f"{label}.plist"

    def yaml_path_for_label(self, label: str) -> Path:
        return self.yaml_dir_for_label(label) / f"{label}.yaml"

    def is_managed_label(self, label: str) -> bool:
        """Return True if the label maps to a configured namespace."""
        try:
            self.namespace_for_label(label)
        except LaunchdCTLError:
            return False
        return True

    def is_prefix_managed_label(self, label: str) -> bool:
        """Return True if the label matches an explicit prefix mapping."""
        return any(label.startswith(prefix) for prefix in self.managed_prefixes)

    def launchd_target(self, label: str) -> str:
        return f"system/{label}"

    def managed_namespace_hint(self) -> str:
        hints = [f"{namespace.prefix}*" for namespace in self.prefix_namespaces]
        if self.default_namespace is not None:
            hints.append(f"default -> {self.default_namespace.yaml_dir}")
        return ", ".join(hints)

    def labels_for_namespace(self, namespace_name: str, labels: Iterable[str]) -> list[str]:
        namespace = self.namespace_by_name(namespace_name)
        if namespace is None:
            raise LaunchdCTLError(f"Unknown namespace: {namespace_name}")
        return sorted(
            label for label in labels if self.namespace_for_label(label).name == namespace.name
        )


def _namespace_from_dict(data: Any) -> NamespaceMapping:
    if not isinstance(data, dict):
        raise LaunchdCTLError("Each namespace entry must be a mapping.")

    name = str(data.get("name") or "").strip()
    if not name:
        raise LaunchdCTLError("Namespace entry requires a non-empty name.")

    prefix = str(data.get("prefix", ""))
    yaml_dir_raw = data.get("yaml_dir")
    if not yaml_dir_raw:
        raise LaunchdCTLError(f"Namespace '{name}' requires yaml_dir.")

    return NamespaceMapping(
        name=name,
        prefix=prefix,
        yaml_dir=Path(yaml_dir_raw).expanduser(),
        chown=_parse_chown(data.get("chown")),
    )
