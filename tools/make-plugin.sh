#!/usr/bin/env bash
# Build show-n-tell.plugin — the Cowork-installable package.
#
# This zips the repo and dereferences symlinks into real files — the
# `skills/show-n-tell/` tree in the source repo points at scripts/,
# helpers/, docs/, etc. via symlinks (one source of truth in the source
# tree); the resulting plugin contains real copies so Cowork's validator,
# which rejects symlinks that escape the skill directory, accepts it.
# The plugin is larger as a result (content is duplicated rather than
# linked) but that's a one-time install artifact, not a dev tree.
#
# Usage:
#   bash tools/make-plugin.sh                       # writes to ./show-n-tell.plugin
#   bash tools/make-plugin.sh /path/to/output/dir   # writes there instead
#
# The `.plugin` file extension is just zip — Cowork's installer recognizes it
# and renders an install card when you hand the file to a Cowork session.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Sanity-check that this is the right repo before we package anything.
[ -f .claude-plugin/plugin.json ] || { echo "✗ .claude-plugin/plugin.json missing — run from the show-n-tell repo root" >&2; exit 1; }
[ -L skills/show-n-tell/SKILL.md ] || { echo "✗ skills/show-n-tell/SKILL.md should be a symlink — repo layout looks wrong" >&2; exit 1; }

OUT_DIR="${1:-$ROOT}"
mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/show-n-tell.plugin"
TMP="$(mktemp -d)"
STAGE="$TMP/show-n-tell.plugin"
trap 'rm -rf "$TMP"' EXIT

# No `-y` flag: zip follows symlinks and stores the dereferenced file
# contents. Required because Cowork's validator rejects symlinks that
# resolve outside the skill directory. The source repo keeps the
# symlinks (single source of truth); the plugin gets real files.
# Excludes: dev-only state that has no business in a distributed plugin.
zip -r "$STAGE" . \
  -x '.git/*' \
  -x '.git' \
  -x '.gitignore' \
  -x '.venv/*' \
  -x '.venv' \
  -x '.pytest_cache/*' \
  -x '.pytest_cache' \
  -x '.playwright-mcp/*' \
  -x '.playwright-mcp' \
  -x '.tmp-explore/*' \
  -x '.tmp-explore' \
  -x '.claude/*' \
  -x '.claude' \
  -x 'tests/*' \
  -x '*.DS_Store' \
  -x '__pycache__/*' \
  -x '*/__pycache__/*' \
  -x 'show-n-tell.plugin' \
  > /dev/null

mv "$STAGE" "$OUT"

echo "✓ built: $OUT"
echo "  size:  $(du -h "$OUT" | cut -f1)"
echo
echo "Install in Cowork: drop the .plugin file into a Cowork chat,"
echo "or hand the path to Claude in a Cowork session and ask to install it."
