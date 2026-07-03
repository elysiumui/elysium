#!/usr/bin/env bash
# Build a single-file Elysium example executable for the current OS.
#
# Usage:
#     scripts/build-example.sh <example-folder-name>
#     scripts/build-example.sh butterfly
#     scripts/build-example.sh hello
#     scripts/build-example.sh --all     # build every discovered example
#
# Output: dist/<os>/Elysium-<ExampleName>
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-./.venv/bin/python}"
[ -x "$PY" ] || PY="python3"

if [ "${1:-}" = "--all" ]; then
    shift
    "$PY" scripts/build.py --list \
        | grep '^example:' \
        | sed 's/^example://' \
        | while read -r name; do
              echo "==> Building example: $name"
              "$PY" scripts/build.py example "$name" "$@"
          done
    exit 0
fi

if [ $# -lt 1 ]; then
    echo "Usage: $0 <example-folder-name> | --all" >&2
    "$PY" scripts/build.py --list | grep '^example:' >&2
    exit 2
fi

exec "$PY" scripts/build.py example "$@"
