#!/usr/bin/env bash
set -euo pipefail

# Fullscreen HDMI display of the realtime transcript (white-on-black, centered).
# Renders via SDL kmsdrm straight to the HDMI output — no desktop required.

RT="/cloud-mirror/Ears/realtime"
PY="/cloud-mirror/Ears/current-venv/bin/python"
PID_FILE="$RT/display.pid"
LOG_FILE="$RT/logs/display.log"

mkdir -p "$RT/logs"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "display already running with pid $(cat "$PID_FILE")"
  exit 0
fi

# render group needed for DRM/KMS on the AMD card
setsid sg render -c "exec '$PY' '$RT/display_hdmi.py'" \
  </dev/null >> "$LOG_FILE" 2>&1 &

echo "$!" > "$PID_FILE"
sleep 2
echo "display started with pid $(cat "$PID_FILE")  (log: $LOG_FILE)"
echo "stop: kill \$(cat $PID_FILE)"
