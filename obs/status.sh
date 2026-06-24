#!/usr/bin/env bash
set -euo pipefail

echo "MediaMTX:"
docker ps --filter name=ears-mediamtx --format '  {{.Names}} {{.Status}} {{.Ports}}'

for name in audio-chunker video-snapshots; do
  pid_file="/cloud-mirror/Ears/obs/$name.pid"
  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "$name: running pid $(cat "$pid_file")"
  else
    echo "$name: stopped"
  fi
done

echo "inbox chunks: $(find /cloud-mirror/Ears/inbox -maxdepth 1 -type f -name '*.wav' | wc -l)"
echo "processed chunks: $(find /cloud-mirror/Ears/processed -maxdepth 1 -type f -name '*.wav' | wc -l)"
