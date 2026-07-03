#!/usr/bin/env bash
# Build a single-file Elysium Designer executable for the current OS
# (macOS or Linux). For Windows, use build-designer.ps1.
#
# Output: dist/<os>/ElysiumDesigner
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-./.venv/bin/python}"
[ -x "$PY" ] || PY="python3"
exec "$PY" scripts/build.py designer "$@"
