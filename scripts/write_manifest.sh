#!/usr/bin/env bash
# Regenerate manifest.json for Posit Connect Cloud from an explicit list of deployable files.
# Builds in a temp copy so local-only files (reference/, private notes, data) can never be listed.
# Run after any change to requirements.txt or to the deployable file set.
set -euo pipefail
cd "$(dirname "$0")/.."

DEPLOY=(app.py requirements.txt .python-version LICENSE NOTICE ite_core modules www)

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
for f in "${DEPLOY[@]}"; do cp -R "$f" "$tmp/"; done
find "$tmp" -name "__pycache__" -type d -prune -exec rm -rf {} +

.venv/bin/rsconnect write-manifest shiny "$tmp" --entrypoint app:app --python .venv/bin/python --overwrite >/dev/null
cp "$tmp/manifest.json" manifest.json
echo "manifest.json written ($(grep -c '"checksum"' manifest.json) files)"
