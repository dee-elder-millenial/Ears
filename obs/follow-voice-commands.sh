#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="/cloud-mirror/Ears/logs/voice-router.log"

touch "$LOG_FILE"
tail -n 40 -f "$LOG_FILE"
