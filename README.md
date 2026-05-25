# launchdctl

CLI tool for managing macOS LaunchDaemons via YAML configs. Namespace routing
(prefix → directory) is fully configurable.

## Quick Start (Examples First)

> Recommendation: when working with system daemons in `/Library/LaunchDaemons`, run commands via `sudo launchdctl ...`.

See what `launchdctl` does before installing:

```bash
# 1) Show current daemon status
launchdctl status

# 2) Export managed plists to YAML files
launchdctl dump

# 3) Preview what would be changed (safe)
launchdctl setup --dry-run

# 4) Check drift for one daemon
launchdctl diff com.example.myapp

# 5) Validate all YAML configs
launchdctl validate
```

Most write operations to `/Library/LaunchDaemons` need `sudo`, for example:

```bash
sudo launchdctl setup --force
sudo launchdctl disable com.example.myapp
sudo launchdctl enable com.example.myapp
```

## Features

- **`dump`** — export plist to YAML
- **`setup`** — apply YAML to plist via `yq` + `plutil` (dry-run + confirmation)
- **`list` / `status`** — list daemons and show status (PID, exit code, disabled)
- **`diff`** — compare installed plist with YAML
- **`validate`** — validate all YAML files
- **`enable` / `disable`** — toggle daemon state via launchctl

## Requirements

- macOS with launchd
- Python 3.10+
- [yq](https://github.com/mikefarah/yq) (`brew install yq`)
- `plutil` (built into macOS)
- optional: `rich` for formatted tables

Commands `setup`, `enable`, `disable`, and writes to `/Library/LaunchDaemons/` require `sudo`.

## Installation

### pip (recommended)

```bash
cd launchdctl
pip install -e ".[rich]"
launchdctl --version
```

### pipx (isolated install)

```bash
pipx install .
```

### Homebrew (tap)

```bash
brew tap roderekh/launchdctl https://github.com/RuBAN-GT/launchdctl
brew install roderekh/launchdctl/launchdctl
```

Upgrade: `brew update && brew upgrade launchdctl`

Details: [`docs/HOMEBREW.md`](docs/HOMEBREW.md)

### Manual deploy (without pip)

```bash
pip install --target /usr/local/lib/launchdctl .
sudo tee /usr/local/bin/launchdctl <<'EOF'
#!/usr/bin/env python3
import sys
sys.path.insert(0, "/usr/local/lib/launchdctl")
from launchdctl.cli import main
raise SystemExit(main())
EOF
sudo chmod +x /usr/local/bin/launchdctl
```

## Configuration

Settings are loaded in this order of precedence:

1. Environment variables
2. Config file (`--config` or `LAUNCHDCTL_CONFIG`)
3. Auto-discovery (first existing file wins):
   - `/etc/launchdctl.yaml` or `/etc/launchdctl.yml`
   - `~/.config/launchdctl/config.yaml` or `config.yml`
   - when run via `sudo`, also checks the invoking user's home (`$SUDO_USER`)
4. Built-in defaults

See [`config.example.yaml`](config.example.yaml) for a generic setup.

### Namespace mapping

Labels are routed to YAML directories by prefix. Longest matching prefix wins.
Unmatched labels fall back to the optional `default` directory.

```yaml
namespaces:
  - name: local
    prefix: local.
    yaml_dir: ~/.local/share/launchdctl/local
  - name: company
    prefix: com.example.
    yaml_dir: ~/.local/share/launchdctl/company

default:
  yaml_dir: ~/.local/share/launchdctl/other
```

CLI filters:

```bash
launchdctl dump --namespace local
launchdctl setup --namespace company --namespace local
```

### Built-in defaults (no config file)

| Setting        | Default                             |
| -------------- | ----------------------------------- |
| YAML directory | `~/.local/share/launchdctl/daemons` |
| Plist path     | `/Library/LaunchDaemons`            |

| Variable                        | Description                            |
| ------------------------------- | -------------------------------------- |
| `LAUNCHDCTL_YAML_DIR`           | Override default YAML directory        |
| `LAUNCHDCTL_CHOWN`              | chown after dump (empty = skip)        |
| `LAUNCHDCTL_DEFAULT_DIR`        | Fallback YAML dir for unmatched labels |
| `LAUNCHDCTL_DEFAULT_CHOWN`      | chown for default namespace            |
| `LAUNCHDCTL_LAUNCH_DAEMONS_DIR` | Plist install path                     |
| `LAUNCHDCTL_CONFIG`             | Path to YAML config                    |

### Personal / machine-specific config

Keep your own mappings in `~/.config/launchdctl/config.yaml`.

```bash
mkdir -p ~/.config/launchdctl
cp config.example.yaml ~/.config/launchdctl/config.yaml
# edit prefixes and paths for your machine
```

## Usage

```bash
# Status (all daemons or one label)
launchdctl status
launchdctl status com.example.myapp

# Export managed daemons to YAML
launchdctl dump
launchdctl dump --namespace local

# Apply YAML back (preview or apply)
launchdctl setup --dry-run
sudo launchdctl setup --force

# Diff plist vs YAML
launchdctl diff com.example.myapp

# Validation
launchdctl validate

# Enable/disable
sudo launchdctl disable com.example.myapp
sudo launchdctl enable com.example.myapp
```

## Project layout

```
launchdctl/
├── pyproject.toml
├── config.example.yaml
├── Formula/launchdctl.rb
├── README.md
└── src/launchdctl/
    ├── cli.py
    ├── config.py
    ├── controller.py
    └── ...
```

## Programmatic use

```python
from launchdctl import Config, LaunchdCTL
from launchdctl.console import Console

config = Config.load()
ctl = LaunchdCTL(Console(verbose=True), config)
status = ctl.get_status("com.example.myapp")
print(status.state, status.pid)
```

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m launchdctl --help
make format
```

## License

MIT
