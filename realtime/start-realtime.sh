#!/usr/bin/env bash
set -euo pipefail

# Launch the dual-engine near-real-time transcriber under the render group
# (so the whisper.cpp correction pass can reach the RX 580 via Vulkan).

RT="/cloud-mirror/Ears/realtime"
PY="/cloud-mirror/Ears/current-venv/bin/python"
PID_FILE="$RT/realtime.pid"
LOG_FILE="$RT/logs/realtime.log"

mkdir -p "$RT/logs"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "realtime transcriber already running with pid $(cat "$PID_FILE")"
  exit 0
fi

# Single mic device — make sure nothing else holds it.
if fuser /dev/snd/pcmC3D0c >/dev/null 2>&1; then
  echo "ERROR: the mic (pcmC3D0c) is held by another process:" >&2
  fuser -v /dev/snd/pcmC3D0c >&2 || true
  echo "Stop it first (e.g. obs/stream_transcribe.py or a chunker)." >&2
  exit 1
fi

setsid sg render -c "exec '$PY' '$RT/realtime_transcribe.py'" \
  </dev/null >> "$LOG_FILE" 2>&1 &

echo "$!" > "$PID_FILE"
echo "realtime transcriber started with pid $(cat "$PID_FILE")"
echo "watch: tail -F $LOG_FILE"
