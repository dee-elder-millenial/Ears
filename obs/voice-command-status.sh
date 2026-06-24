#!/usr/bin/env bash
set -euo pipefail

OBS_DIR="/cloud-mirror/Ears/obs"
COMMANDS_DIR="/cloud-mirror/Ears/commands"

for name in voice-router watch-transcribe audio-chunker; do
  pid_file="$OBS_DIR/$name.pid"
  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "$name: running pid $(cat "$pid_file")"
  else
    echo "$name: stopped"
  fi
done

if [[ -f "$COMMANDS_DIR/status.json" ]]; then
  echo "status:"
  cat "$COMMANDS_DIR/status.json"
fi

echo "approved commands: $(find "$COMMANDS_DIR" -maxdepth 1 -type f -name 'approved.jsonl' -exec wc -l {} + 2>/dev/null | awk '{print $1}' || echo 0)"
