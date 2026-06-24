#!/usr/bin/env bash
set -euo pipefail

EARS_DIR="/cloud-mirror/Ears"
FFMPEG="$EARS_DIR/bin/ffmpeg"
PID_FILE="$EARS_DIR/obs/audio-chunker.pid"
LOG_FILE="$EARS_DIR/logs/audio-chunker.log"
SEGMENT_TIME="${SEGMENT_TIME:-8}"
STREAM_URL="${STREAM_URL:-rtmp://127.0.0.1:1935/live/ears}"

mkdir -p "$EARS_DIR/inbox" "$EARS_DIR/logs" "$EARS_DIR/obs"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "audio chunker already running with pid $(cat "$PID_FILE")"
  exit 0
fi

setsid "$FFMPEG" \
  -nostdin \
  -hide_banner \
  -loglevel info \
  -i "$STREAM_URL" \
  -vn \
  -ac 1 \
  -ar 16000 \
  -acodec pcm_s16le \
  -f segment \
  -segment_time "$SEGMENT_TIME" \
  -reset_timestamps 1 \
  -strftime 1 \
  "$EARS_DIR/inbox/obs-%Y%m%dT%H%M%SZ.wav" \
  </dev/null >> "$LOG_FILE" 2>&1 &

echo "$!" > "$PID_FILE"
echo "audio chunker started with pid $(cat "$PID_FILE")"
