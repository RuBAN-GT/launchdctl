# Homebrew tap install

Install via personal tap `roderekh/launchdctl` from GitHub repo `RuBAN-GT/launchdctl`.

Tap nickname and GitHub org do not have to match.

## Install (any Mac)

```bash
brew tap roderekh/launchdctl https://github.com/RuBAN-GT/launchdctl
brew install roderekh/launchdctl/launchdctl
```

Dependencies (`yq`, `python@3.13`) are installed automatically.

Verify:

```bash
launchdctl --version
brew test launchdctl
```

## Config after install

```bash
mkdir -p ~/.config/launchdctl
cp "$(brew --prefix)/share/launchdctl/config.example.yaml" \
   ~/.config/launchdctl/config.yaml
```

## Upgrade

```bash
brew update
brew upgrade launchdctl
```

## Install latest master (dev)

```bash
brew tap roderekh/launchdctl https://github.com/RuBAN-GT/launchdctl
brew install --HEAD roderekh/launchdctl/launchdctl
```

## Uninstall

```bash
brew uninstall launchdctl
brew untap roderekh/launchdctl
```

## Maintainer: new release

When you bump version in `pyproject.toml` and push a new git tag:

```bash
git tag v1.0.1
git push origin master --tags

./scripts/brew-formula-bump.sh 1.0.1
git add Formula/launchdctl.rb pyproject.toml src/launchdctl/__version__.py
git commit -m "Release v1.0.1"
git push
```

Users then run `brew update && brew upgrade launchdctl`.

## Local formula test (before push)

```bash
brew tap --force-local launchdctl/local "$(pwd)"
brew install --build-from-source launchdctl/local/launchdctl
brew test launchdctl
brew audit --strict "$(brew --repository launchdctl/local)/Formula/launchdctl.rb"
brew untap launchdctl/local
```

## Troubleshooting

If `launchdctl` is not found after a failed install:

```bash
brew uninstall launchdctl 2>/dev/null || true
brew cleanup launchdctl
brew tap roderekh/launchdctl https://github.com/RuBAN-GT/launchdctl
brew install roderekh/launchdctl/launchdctl
```

If you previously tapped an old or broken copy of this formula, remove it first:

```bash
brew untap <user>/launchdctl
```

## Tap layout in this repo

```
launchdctl/
└── Formula/
    └── launchdctl.rb
```

Homebrew accepts a tap from any GitHub repo that contains a `Formula/` directory.
