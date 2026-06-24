#!/usr/bin/env bash
set -euo pipefail

PID_FILE="/cloud-mirror/Ears/obs/video-snapshots.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "video snapshots are not running"
  exit 0
fi

PID="$(cat "$PID_FILE")"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "stopped video snapshots pid $PID"
else
  echo "video snapshots pid $PID is not active"
fi

rm -f "$PID_FILE"
