#!/usr/bin/env bash
set -euo pipefail

PID_FILE="/cloud-mirror/Ears/obs/audio-chunker.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "audio chunker is not running"
  exit 0
fi

PID="$(cat "$PID_FILE")"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "stopped audio chunker pid $PID"
else
  echo "audio chunker pid $PID is not active"
fi

rm -f "$PID_FILE"
