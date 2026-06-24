from __future__ import annotations

import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from faster_whisper import WhisperModel

EARS_DIR = Path("/cloud-mirror/Ears")
INBOX = EARS_DIR / "inbox"
PROCESSED = EARS_DIR / "processed"
TRANSCRIPTS = EARS_DIR / "transcripts"
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small.en")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
ERRORS = EARS_DIR / "errors"
MIN_AGE_SECONDS = 1.0   # let ffmpeg finish flushing a segment before we read it
POLL_SECONDS = 0.5


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def chunker_running() -> bool:
    pid_file = EARS_DIR / "obs" / "mic-chunker.pid"
    if not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except ValueError:
        return False
    return Path(f"/proc/{pid}").exists()


def main() -> None:
    for directory in (INBOX, PROCESSED, TRANSCRIPTS, ERRORS):
        directory.mkdir(parents=True, exist_ok=True)

    live_text = TRANSCRIPTS / "live-transcript.txt"
    jsonl = TRANSCRIPTS / "messages.jsonl"

    print(f"loading model {WHISPER_MODEL} ({WHISPER_COMPUTE_TYPE}, {WHISPER_DEVICE}) + Silero VAD...", flush=True)
    model = WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
    print("live transcriber ready; listening for new chunks", flush=True)

    while True:
        files = [
            path for path in sorted(INBOX.glob("*.wav"))
            if time.time() - path.stat().st_mtime >= MIN_AGE_SECONDS
        ]
        # The newest segment is the one ffmpeg is still writing; its WAV header
        # is not finalized until rotation, so never touch the last file while
        # the chunker is alive. (Mirrors transcribe_inbox_once.py.)
        if len(files) >= 1 and chunker_running():
            files = files[:-1]
        for path in files:
            try:
                segments, info = model.transcribe(str(path), beam_size=5, vad_filter=True)
                text = " ".join(seg.text.strip() for seg in segments).strip()
            except Exception as error:  # quarantine unreadable chunks, keep going
                destination = ERRORS / path.name
                shutil.move(str(path), destination)
                print(f"quarantined {path.name}: {error}", flush=True)
                continue

            record = {
                "created_at": utc_now(),
                "file": str(path),
                "language": info.language,
                "language_probability": info.language_probability,
                "text": text,
            }
            with live_text.open("a", encoding="utf-8") as handle:
                handle.write(f"[{record['created_at']}] {path.name}: {text}\n")
            with jsonl.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=True) + "\n")

            destination = PROCESSED / path.name
            if destination.exists():
                destination = PROCESSED / f"{path.stem}-{int(time.time())}{path.suffix}"
            shutil.move(str(path), destination)

            if text:
                print(f"[{record['created_at']}]  {text}", flush=True)

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("live transcriber stopped", flush=True)
        sys.exit(0)
