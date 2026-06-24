from __future__ import annotations

"""Near-real-time mic transcriber for Ears (Silero VAD endpointing).

Reads raw PCM continuously from the USB mic via `arecord`, runs Silero neural
VAD per 32ms window to detect speech, and transcribes each utterance from
memory the moment the speaker pauses. Emits the same transcripts/messages.jsonl
records the file-based pipeline does, so the voice router can consume them.

No fixed time window and no noise-floor calibration: latency is ~hangover +
compute, and Silero judges speech spectrally so a high/noisy mic floor is fine.
"""

import json
import os
import signal
import subprocess
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel
from faster_whisper import vad as fw_vad

EARS_DIR = Path("/cloud-mirror/Ears")
TRANSCRIPTS = EARS_DIR / "transcripts"
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small.en")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")

MIC_DEVICE = os.environ.get("MIC_DEVICE", "plughw:CARD=CODEC,DEV=0")
RATE = 16000
FRAME_SAMPLES = 512                  # Silero v5 window size at 16kHz (32ms)
FRAME_BYTES = FRAME_SAMPLES * 2      # int16 mono
FRAME_MS = FRAME_SAMPLES * 1000 // RATE

VAD_THRESHOLD = float(os.environ.get("VAD_THRESHOLD", "0.5"))
PREROLL_MS = 320                     # audio kept before speech onset
HANGOVER_MS = 700                    # trailing silence that ends an utterance
ATTACK_MS = 96                       # consecutive speech windows needed to start
MIN_UTTERANCE_MS = 250              # ignore shorter blips
MAX_UTTERANCE_S = 12.0              # force a flush during long talking

_stop = False


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def handle_stop(*_a) -> None:
    global _stop
    _stop = True


def open_mic() -> subprocess.Popen:
    return subprocess.Popen(
        ["arecord", "-D", MIC_DEVICE, "-f", "S16_LE", "-r", str(RATE),
         "-c", "1", "-t", "raw", "-q"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )


def read_frame(proc: subprocess.Popen) -> np.ndarray | None:
    buf = proc.stdout.read(FRAME_BYTES)
    if not buf or len(buf) < FRAME_BYTES:
        return None
    return np.frombuffer(buf, dtype=np.int16)


def main() -> None:
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
    jsonl = TRANSCRIPTS / "messages.jsonl"
    live_text = TRANSCRIPTS / "live-transcript.txt"

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    print(f"loading model {WHISPER_MODEL} ({WHISPER_COMPUTE_TYPE}, {WHISPER_DEVICE}) + Silero VAD...", flush=True)
    model = WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
    vad_model = fw_vad.get_vad_model()

    def speech_prob(frame_i16: np.ndarray) -> float:
        f = frame_i16.astype(np.float32) / 32768.0
        out = np.asarray(vad_model(f)).reshape(-1)
        return float(out[-1])

    proc = open_mic()
    if proc.stdout is None:
        print("failed to open mic", flush=True)
        sys.exit(1)
    print(f"stream transcriber ready (VAD>={VAD_THRESHOLD}); speak and pause to flush",
          flush=True)

    preroll = deque(maxlen=max(1, PREROLL_MS // FRAME_MS))
    hangover_frames = max(1, HANGOVER_MS // FRAME_MS)
    attack_frames = max(1, ATTACK_MS // FRAME_MS)
    min_speech_frames = max(1, MIN_UTTERANCE_MS // FRAME_MS)
    max_frames = int(MAX_UTTERANCE_S * 1000 / FRAME_MS)

    in_speech = False
    loud_streak = 0
    silence_run = 0
    speech_frames: list[np.ndarray] = []

    def flush(reason: str) -> None:
        nonlocal speech_frames, in_speech, silence_run, loud_streak
        if len(speech_frames) >= min_speech_frames:
            audio = np.concatenate(speech_frames).astype(np.float32) / 32768.0
            t0 = time.monotonic()
            segments, info = model.transcribe(audio, beam_size=5, vad_filter=False,
                                              language="en")
            text = " ".join(s.text.strip() for s in segments).strip()
            took = time.monotonic() - t0
            if text:
                stamp = utc_now()
                record = {"created_at": stamp, "file": None, "language": info.language,
                          "language_probability": info.language_probability, "text": text}
                with jsonl.open("a", encoding="utf-8") as h:
                    h.write(json.dumps(record, ensure_ascii=True) + "\n")
                with live_text.open("a", encoding="utf-8") as h:
                    h.write(f"[{stamp}] stream: {text}\n")
                print(f"[{stamp}] ({took:.2f}s,{reason})  {text}", flush=True)
        speech_frames = []
        in_speech = False
        silence_run = 0
        loud_streak = 0

    while not _stop:
        frame = read_frame(proc)
        if frame is None:
            time.sleep(0.02)
            if proc.poll() is not None:          # arecord died; restart it
                proc = open_mic()
            continue

        is_speech = speech_prob(frame) >= VAD_THRESHOLD
        if not in_speech:
            preroll.append(frame)
            loud_streak = loud_streak + 1 if is_speech else 0
            if loud_streak >= attack_frames:     # confirmed onset
                in_speech = True
                silence_run = 0
                speech_frames = list(preroll)    # include pre-roll + attack ramp
        else:
            speech_frames.append(frame)
            silence_run = 0 if is_speech else silence_run + 1
            if silence_run >= hangover_frames:
                flush("pause")
            elif len(speech_frames) >= max_frames:
                flush("maxlen")

    proc.terminate()
    print("stream transcriber stopped", flush=True)


if __name__ == "__main__":
    main()
