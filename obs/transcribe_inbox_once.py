from __future__ import annotations

import json
import shutil
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from faster_whisper import WhisperModel

EARS_DIR = Path("/cloud-mirror/Ears")
INBOX = EARS_DIR / "inbox"
PROCESSED = EARS_DIR / "processed"
TRANSCRIPTS = EARS_DIR / "transcripts"
LOGS = EARS_DIR / "logs"
ERRORS = EARS_DIR / "errors"
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small.en")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
MIN_AGE_SECONDS = 2


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def audio_chunker_running() -> bool:
    pid_file = EARS_DIR / "obs" / "audio-chunker.pid"
    if not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except ValueError:
        return False
    return Path(f"/proc/{pid}").exists()


def main() -> None:
    INBOX.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    ERRORS.mkdir(parents=True, exist_ok=True)

    files = [
        path for path in sorted(INBOX.glob("*.wav"))
        if time.time() - path.stat().st_mtime >= MIN_AGE_SECONDS
    ]

    if audio_chunker_running() and files:
        files = files[:-1]

    if not files:
        print("No completed WAV chunks found.")
        return

    print(f"loading model {WHISPER_MODEL} ({WHISPER_COMPUTE_TYPE}, {WHISPER_DEVICE})...", flush=True)
    model = WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)

    live_text = TRANSCRIPTS / "live-transcript.txt"
    jsonl = TRANSCRIPTS / "messages.jsonl"

    for path in files:
        try:
            segments, info = model.transcribe(str(path), beam_size=5, vad_filter=True)
        except Exception as error:
            destination = ERRORS / path.name
            if destination.exists():
                destination = ERRORS / f"{path.stem}-{int(time.time())}{path.suffix}"
            shutil.move(str(path), destination)
            print(f"quarantined {path.name}: {error}")
            continue

        text = " ".join(segment.text.strip() for segment in segments).strip()
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
        print(f"transcribed {path.name}: {text}")


if __name__ == "__main__":
    main()
