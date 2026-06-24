#!/usr/bin/env bash
set -euo pipefail

EARS_DIR="/cloud-mirror/Ears"
PYTHON="$EARS_DIR/current-venv/bin/python"

"$PYTHON" "$EARS_DIR/obs/transcribe_inbox_once.py"
