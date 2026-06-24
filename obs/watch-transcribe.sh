#!/usr/bin/env bash
set -euo pipefail

EARS_DIR="/cloud-mirror/Ears"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-4}"

mkdir -p "$EARS_DIR/logs" "$EARS_DIR/transcripts"

echo "watch-transcribe started at $(date -u +%Y-%m-%dT%H:%M:%SZ)"

while true; do
  "$EARS_DIR/obs/transcribe-inbox-once.sh"
  sleep "$INTERVAL_SECONDS"
done
