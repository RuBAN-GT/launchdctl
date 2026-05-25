#!/usr/bin/env bash
# Update Formula/launchdctl.rb url + sha256 for a GitHub release tag.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FORMULA="$ROOT/Formula/launchdctl.rb"

OWNER="${GITHUB_OWNER:-RuBAN-GT}"
REPO="${GITHUB_REPO:-launchdctl}"
VERSION="${1:-}"

if [[ -z "$VERSION" ]]; then
  VERSION="$(grep '^version = ' "$ROOT/pyproject.toml" | sed 's/version = "\(.*\)"/\1/')"
fi

TAG="v${VERSION#v}"
URL="https://github.com/${OWNER}/${REPO}/archive/refs/tags/${TAG}.tar.gz"

echo "Version: $VERSION"
echo "URL:     $URL"

SHA256="$(curl -fsSL "$URL" | shasum -a 256 | awk '{print $1}')"
echo "sha256:  $SHA256"

perl -0pi -e "s|url \"https://github.com/[^\"]+\"|url \"$URL\"|" "$FORMULA"
perl -0pi -e "s|sha256 \"[^\"]+\"|sha256 \"$SHA256\"|" "$FORMULA"

echo "Updated $FORMULA"
