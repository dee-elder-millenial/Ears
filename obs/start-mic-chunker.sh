#!/usr/bin/env bash
set -euo pipefail

# Direct-USB-mic variant of start-audio-chunker.sh.
# Reads from an ALSA capture device instead of the OBS/RTMP stream and writes
# gapless 8s WAV chunks into inbox/ for the transcriber to pick up.

EARS_DIR="/cloud-mirror/Ears"
FFMPEG="$EARS_DIR/bin/ffmpeg"
PID_FILE="$EARS_DIR/obs/mic-chunker.pid"
LOG_FILE="$EARS_DIR/logs/mic-chunker.log"
SEGMENT_TIME="${SEGMENT_TIME:-8}"
# Stable ALSA name so it survives card-number reshuffles on reboot/replug.
MIC_DEVICE="${MIC_DEVICE:-plughw:CARD=CODEC,DEV=0}"

mkdir -p "$EARS_DIR/inbox" "$EARS_DIR/logs" "$EARS_DIR/obs"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "mic chunker already running with pid $(cat "$PID_FILE")"
  exit 0
fi

setsid "$FFMPEG" \
  -nostdin \
  -hide_banner \
  -loglevel info \
  -f alsa \
  -thread_queue_size 512 \
  -i "$MIC_DEVICE" \
  -ac 1 \
  -ar 16000 \
  -acodec pcm_s16le \
  -f segment \
  -segment_time "$SEGMENT_TIME" \
  -reset_timestamps 1 \
  -strftime 1 \
  "$EARS_DIR/inbox/mic-%Y%m%dT%H%M%SZ.wav" \
  </dev/null >> "$LOG_FILE" 2>&1 &

echo "$!" > "$PID_FILE"
echo "mic chunker started with pid $(cat "$PID_FILE") on device $MIC_DEVICE"
