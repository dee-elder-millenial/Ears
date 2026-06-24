#!/usr/bin/env bash
set -euo pipefail

OBS_DIR="/cloud-mirror/Ears/obs"

stop_pid_file() {
  local label="$1"
  local pid_file="$2"
  if [[ ! -f "$pid_file" ]]; then
    echo "$label is not running"
    return
  fi

  local pid
  pid="$(cat "$pid_file")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    echo "stopped $label pid $pid"
  else
    echo "$label pid $pid is not active"
  fi
  rm -f "$pid_file"
}

stop_pid_file "voice-router" "$OBS_DIR/voice-router.pid"
stop_pid_file "watch-transcribe" "$OBS_DIR/watch-transcribe.pid"
"$OBS_DIR/stop-audio-chunker.sh"
