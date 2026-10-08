#!/usr/bin/env bash
#
# oh-my-kiro installer for Kiro CLI V3.
#
# Downloads the power tarball (no git required) and installs it with
# `kiro-cli --v3 powers install <dir>`.
#
# Usage:
#   ./install.sh                 # install the latest main
#   ./install.sh --ref v0.1.0    # install a tag/branch/commit
#
# One-liner (no clone):
#   curl -fsSL https://raw.githubusercontent.com/oniharnantyo/oh-my-kiro/main/install.sh | bash
#
set -euo pipefail

REPO="oniharnantyo/oh-my-kiro"
REF="main"

while [ $# -gt 0 ]; do
  case "$1" in
    --ref)
      REF="${2:?--ref requires a value, e.g. --ref v0.1.0}"
      shift 2
      ;;
    -h|--help)
      sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      echo "usage: $0 [--ref <tag|branch|commit>]" >&2
      exit 2
      ;;
  esac
done

if ! command -v kiro-cli >/dev/null 2>&1; then
  echo "error: kiro-cli not found on PATH." >&2
  echo "Install Kiro CLI first: https://kiro.dev/docs/cli/" >&2
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "oh-my-kiro installer"
echo "  repo : $REPO"
echo "  ref  : $REF"

URL="https://github.com/$REPO/archive/$REF.tar.gz"

echo "  url  : $URL"
echo "downloading..."

if ! curl -fsSL "$URL" | tar -xz -C "$TMP" --strip-components=1; then
  echo "error: download or extraction failed." >&2
  echo "Check that ref '$REF' exists: https://github.com/$REPO" >&2
  exit 1
fi

if [ ! -f "$TMP/plugin.json" ]; then
  echo "error: downloaded archive has no plugin.json at its root." >&2
  exit 1
fi

echo "installing power..."
( cd "$TMP" && kiro-cli --v3 powers install . )

cat <<'EOF'

done. The power is installed.

Next step (required): open a Kiro session and run

    /setup

It asks for scope (project or global) and a cost preset (cheap/medium/premium/openai),
then installs the team worker agents, hooks, and steering.
EOF
