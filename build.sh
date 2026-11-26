#!/bin/sh
# ExTetris build (macOS / Linux): tests -> validate -> quick balance check -> packages in dist/
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
"$PY" -m pip install --quiet numpy pytest
"$PY" -m pytest v1_core_system v2_platform_release -q
for v in variants/*.toml; do
  "$PY" v2_platform_release/cli.py validate "$v"
  "$PY" v2_platform_release/cli.py simulate "$v" --games "${GAMES:-20}"
  "$PY" v2_platform_release/cli.py package "$v" --pyinstaller
done
echo "Build complete: see dist/"
