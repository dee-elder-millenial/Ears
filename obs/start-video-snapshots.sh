#!/usr/bin/env bash
set -euo pipefail

EARS_DIR="/cloud-mirror/Ears"
FFMPEG="$EARS_DIR/bin/ffmpeg"
PID_FILE="$EARS_DIR/obs/video-snapshots.pid"
LOG_FILE="$EARS_DIR/logs/video-snapshots.log"
STREAM_URL="${STREAM_URL:-rtmp://127.0.0.1:1935/live/ears}"
SNAPSHOT_SECONDS="${SNAPSHOT_SECONDS:-5}"

mkdir -p "$EARS_DIR/video" "$EARS_DIR/logs" "$EARS_DIR/obs"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "video snapshots already running with pid $(cat "$PID_FILE")"
  exit 0
fi

setsid "$FFMPEG" \
  -nostdin \
  -hide_banner \
  -loglevel warning \
  -i "$STREAM_URL" \
  -vf "fps=1/$SNAPSHOT_SECONDS" \
  -q:v 3 \
  -strftime 1 \
  "$EARS_DIR/video/frame-%Y%m%dT%H%M%SZ.jpg" \
  </dev/null >> "$LOG_FILE" 2>&1 &

echo "$!" > "$PID_FILE"
echo "video snapshots started with pid $(cat "$PID_FILE")"
