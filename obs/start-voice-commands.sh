#!/usr/bin/env bash
set -euo pipefail

EARS_DIR="/cloud-mirror/Ears"
OBS_DIR="$EARS_DIR/obs"
COMMANDS_DIR="$EARS_DIR/commands"
LOG_DIR="$EARS_DIR/logs"
SESSION_ID="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE_DIR="$EARS_DIR/sessions/$SESSION_ID/archive-start-inbox"
WATCH_PID="$OBS_DIR/watch-transcribe.pid"
ROUTER_PID="$OBS_DIR/voice-router.pid"

mkdir -p "$COMMANDS_DIR" "$LOG_DIR" "$ARCHIVE_DIR"

if [[ -f "$WATCH_PID" ]] && kill -0 "$(cat "$WATCH_PID")" 2>/dev/null; then
  echo "voice command transcriber already running with pid $(cat "$WATCH_PID")"
  exit 0
fi

if [[ -f "$ROUTER_PID" ]] && kill -0 "$(cat "$ROUTER_PID")" 2>/dev/null; then
  echo "voice command router already running with pid $(cat "$ROUTER_PID")"
  exit 0
fi

"$OBS_DIR/stop-audio-chunker.sh" >/dev/null || true

find "$EARS_DIR/inbox" -maxdepth 1 -type f -name '*.wav' -exec mv {} "$ARCHIVE_DIR"/ \;

"$OBS_DIR/start-audio-chunker.sh"

setsid "$OBS_DIR/watch-transcribe.sh" \
  </dev/null >> "$LOG_DIR/watch-transcribe.log" 2>&1 &
echo "$!" > "$WATCH_PID"

setsid "$EARS_DIR/current-venv/bin/python" "$OBS_DIR/voice_router.py" \
  </dev/null >> "$LOG_DIR/voice-router.log" 2>&1 &
echo "$!" > "$ROUTER_PID"

echo "voice command session started"
echo "session: $SESSION_ID"
echo "watch-transcribe pid: $(cat "$WATCH_PID")"
echo "voice-router pid: $(cat "$ROUTER_PID")"
echo "archived prior inbox chunks to: $ARCHIVE_DIR"
