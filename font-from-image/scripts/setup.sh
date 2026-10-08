#!/usr/bin/env bash
# Create a virtualenv with everything the font-from-image scripts need.
# Usage: scripts/setup.sh [venv-dir]   (default: ./.venv in the current project)
set -e
VENV="${1:-.venv}"
if [ ! -d "$VENV" ]; then python3 -m venv "$VENV"; fi
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q fonttools potracer numpy scipy pillow scikit-image brotli
echo "ok: $VENV/bin/python"
