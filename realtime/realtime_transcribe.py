from __future__ import annotations

"""Ears dual-engine near-real-time transcription.

One integrated program:

  capture (arecord) ──▶ Vosk draft pass (CPU, instant partial words)
                            │  on end-of-utterance (silence)
                            ▼
                    whisper.cpp correction pass (RX 580 / Vulkan)
                            │
                            ▼
              corrected line ──▶ stdout/log + transcripts/messages.jsonl

Pass 1 (Vosk) streams provisional words ~instantly as you speak. Pass 2
(whisper.cpp on the GPU) re-transcribes each finished utterance and replaces
the draft with an accurate line. The two run on different compute units.

Run it under the render group so the whisper subprocess can reach the GPU:
  sg render -c '.../python realtime_transcribe.py'
(start-realtime.sh does this for you.)
"""

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

from vosk import Model, KaldiRecognizer, SetLogLevel

EARS = Path("/cloud-mirror/Ears")
RT = EARS / "realtime"
TRANSCRIPTS = EARS / "transcripts"
WORDS_JSONL = RT / "logs" / "words.jsonl"   # per-word confidence feed for the display
UTTERANCES_JSONL = TRANSCRIPTS / "utterances.jsonl"   # instant Vosk finals (fast convo feed)
MUTE_FLAG = RT / "mute"                      # while this file exists, discard mic audio
                                             # (so Claude's own TTS doesn't get transcribed)

MIC_DEVICE = os.environ.get("MIC_DEVICE", "plughw:CARD=CODEC,DEV=0")
RATE = 16000
READ_BYTES = 4000                       # ~0.125s of int16 mono per read

# Large model for accurate live first-guesses (slower to load + a touch more
# latency than the small model, but much better words). Set VOSK_MODEL to the
# small model path for a faster/lighter run.
VOSK_MODEL = os.environ.get("VOSK_MODEL", str(RT / "models" / "vosk-model-en-us-0.22"))
WHISPER_CLI = str(RT / "whisper.cpp" / "build" / "bin" / "whisper-cli")
# Accuracy-first default (medium.en has the best clean-up quality we've had so far).
# Swap to .../ggml-small.en.bin for faster turns, or ggml-base.en.bin for
# the quickest passes at lower fidelity.
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", str(RT / "models" / "ggml-medium.en.bin"))

# Vosk hallucinates a lone filler word (esp. "the") on silence/noise. Drop an
# utterance that is nothing but one of these so it never reaches the screen,
# the fast feed, or the whisper pass.
FILLER_WORDS = {"the", "a", "an", "and", "um", "uh", "so", "i", "you", "it",
                "to", "of", "huh", "hmm", "yeah", "oh"}


def is_filler_noise(text: str) -> bool:
    w = text.lower().strip(" .,?!")
    return w in FILLER_WORDS
WHISPER_THREADS = os.environ.get("WHISPER_THREADS", "4")
TMPDIR = Path(os.environ.get("EARS_RT_TMP", "/cloud-mirror/temp/ears-rt"))

# Bias the GPU correction pass with the Vosk draft as an initial prompt
# ("autocomplete head-start"). OFF by default: the small Vosk model's drafts
# are often garbled and a bad prompt drags whisper off the rails. Enable with
# PROMPT_BIAS=1 once a stronger draft model is in use.
PROMPT_BIAS = os.environ.get("PROMPT_BIAS", "0") == "1"
KEEP_WAV = os.environ.get("EARS_RT_KEEP_WAV", "0") == "1"  # retain utt wavs for debugging


WHISPER_LABEL = "whisper-" + Path(WHISPER_MODEL).stem.replace("ggml-", "")
# whisper emits bracketed non-speech annotations like "(dramatic music)",
# "[BLANK_AUDIO]", "[silence]" on short/ambiguous audio. Drop output that is
# only such annotations and fall back to the draft.
NONSPEECH_RE = re.compile(r"^[\s]*([\(\[][^\)\]]*[\)\]][\s]*)+$")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def strip_nonspeech(text: str) -> str:
    """Return '' if text is nothing but bracketed non-speech annotations."""
    return "" if NONSPEECH_RE.match(text) else text


WHISPER_MARK_RE = re.compile(r"<\|[^|]*\|>")     # e.g. <|endoftext|>, <|0.00|>


def parse_whisper_words(json_path: Path) -> list[tuple[str, float, int]]:
    """Parse whisper.cpp JSON-full into [(word, confidence, t_start_ms)] by
    grouping tokens into words (a token whose text starts with a space begins a
    new word), averaging token probabilities, and taking each word's start
    offset. Skips special/bracket/<|...|> tokens. The t_start lets the display
    replay words at the cadence they were actually spoken."""
    data = json.loads(json_path.read_text(encoding="utf-8"))
    words: list[tuple[str, float, int]] = []
    cur, probs, t0 = "", [], 0

    def flush():
        nonlocal cur, probs, t0
        w = WHISPER_MARK_RE.sub("", cur).strip()
        if w and not NONSPEECH_RE.match(w):
            conf = sum(probs) / len(probs) if probs else 0.0
            words.append((w, round(conf, 3), int(t0)))
        cur, probs = "", []

    for seg in data.get("transcription", []):
        for tok in seg.get("tokens", []):
            txt = tok.get("text", "")
            s = txt.strip()
            if not s or (s.startswith("[") and s.endswith("]")) or \
               (s.startswith("<|") and s.endswith("|>")):
                continue                       # special token
            if txt.startswith(" ") and cur:    # space => new word boundary
                flush()
            if not cur:                        # first token of a word: capture start ms
                t0 = (tok.get("offsets") or {}).get("from", 0)
            cur += txt
            probs.append(float(tok.get("p", 0.0)))
    flush()
    return words


SPEECH_PAD_S = 0.20   # keep a little audio either side of the spoken span


def trim_to_speech(pcm: bytes, words: list[dict]) -> bytes:
    """Slice raw PCM to the spoken span [first word start, last word end] using
    Vosk word timestamps, with small padding. Falls back to the full buffer if
    timestamps are absent. This removes the silent padding that makes whisper
    hallucinate filler phrases on short utterances."""
    if not words:
        return pcm
    start = max(0.0, float(words[0].get("start", 0.0)) - SPEECH_PAD_S)
    end = float(words[-1].get("end", 0.0)) + SPEECH_PAD_S
    b0 = int(start * RATE) * 2          # *2: int16 mono
    b1 = int(end * RATE) * 2
    clip = pcm[b0:b1]
    return clip if clip else pcm


def write_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)


class Transcriber:
    def __init__(self) -> None:
        TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
        TMPDIR.mkdir(parents=True, exist_ok=True)
        self.jsonl = TRANSCRIPTS / "messages.jsonl"
        self.live_text = TRANSCRIPTS / "live-transcript.txt"
        self.correct_q: "queue.Queue[tuple[int,bytes,str]]" = queue.Queue()
        self.counter = 0
        self.stop = False
        self.last_partial = ""
        self.emitted = 0          # how many words of the current utterance are on-screen

    def emit_words(self, new_words: list[str], conf: float = 0.9) -> None:
        """Push freshly-spoken words to the display feed immediately (live),
        so the screen flows with speech instead of firing a whole sentence
        at once. These are Vosk's live words; whisper still corrects the record."""
        if not new_words:
            return
        with WORDS_JSONL.open("a", encoding="utf-8") as h:
            h.write(json.dumps({"live": True,
                                "words": [[w, conf, 0] for w in new_words]},
                               ensure_ascii=True) + "\n")

    # ---- Pass 2: GPU correction worker -------------------------------------
    def correction_worker(self) -> None:
        while not self.stop:
            try:
                uid, pcm, draft = self.correct_q.get(timeout=0.3)
            except queue.Empty:
                continue
            wav = TMPDIR / f"utt-{uid}.wav"
            jbase = TMPDIR / f"utt-{uid}"
            jpath = TMPDIR / f"utt-{uid}.json"
            try:
                write_wav(wav, pcm)
                cmd = [WHISPER_CLI, "-m", WHISPER_MODEL, "-f", str(wav),
                       "-t", WHISPER_THREADS, "-nt", "-np", "-l", "en",
                       "--suppress-nst", "-ojf", "-of", str(jbase),
                       # anti-hallucination, reins slightly loosened: -mc 32 lets
                       # whisper use a little decoded context (better coherence)
                       # without the unlimited carryover that auto-finishes known
                       # poems; -nf still disables the creative-retry path.
                       "-mc", "32", "-nf"]
                if PROMPT_BIAS and draft:
                    cmd += ["--prompt", draft]
                t0 = time.monotonic()
                subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                took = (time.monotonic() - t0) * 1000
                words = parse_whisper_words(jpath) if jpath.exists() else []
                if words:
                    self.commit(uid, words, draft, took)
                else:
                    # nothing usable from whisper; keep the draft so we don't lose it
                    fallback = [(w, 0.4, i * 300) for i, w in enumerate(draft.split())]
                    if fallback:
                        self.commit(uid, fallback, draft, took, engine="vosk-draft")
            except Exception as error:  # never let one utterance kill the worker
                print(f"  [correction error uid={uid}: {error}]", flush=True)
                fallback = [(w, 0.4, i * 300) for i, w in enumerate(draft.split())]
                if fallback:
                    self.commit(uid, fallback, draft, 0.0, engine="vosk-draft")
            finally:
                if not KEEP_WAV:
                    wav.unlink(missing_ok=True)
                jpath.unlink(missing_ok=True)
                self.correct_q.task_done()

    def commit(self, uid: int, words: list[tuple[str, float, int]], draft: str,
               took_ms: float, engine: str = WHISPER_LABEL) -> None:
        stamp = utc_now()
        text = " ".join(w for w, _, _ in words)
        avg = sum(c for _, c, _ in words) / len(words) if words else 0.0
        print(f"FINAL[{uid}]> {text}    [{engine}, {took_ms:.0f}ms, conf {avg:.2f}]",
              flush=True)
        record = {
            "created_at": stamp, "file": None, "source": "realtime",
            "engine": engine, "correction_ms": round(took_ms),
            "draft_text": draft, "text": text, "words": words,
        }
        with self.jsonl.open("a", encoding="utf-8") as h:
            h.write(json.dumps(record, ensure_ascii=True) + "\n")
        with self.live_text.open("a", encoding="utf-8") as h:
            h.write(f"[{stamp}] realtime: {text}\n")
        # NOTE: the HDMI display feeds from the LIVE Vosk word stream (emit_words)
        # so the screen flows with speech; whisper text is kept here for the record.

    # ---- Pass 1: Vosk draft + capture --------------------------------------
    def run(self) -> None:
        SetLogLevel(-1)
        print(f"loading Vosk model: {VOSK_MODEL}", flush=True)
        model = Model(VOSK_MODEL)
        rec = KaldiRecognizer(model, RATE)
        rec.SetWords(True)   # per-word timestamps, used to trim silence before whisper

        worker = threading.Thread(target=self.correction_worker, daemon=True)
        worker.start()

        proc = subprocess.Popen(
            ["arecord", "-D", MIC_DEVICE, "-f", "S16_LE", "-r", str(RATE),
             "-c", "1", "-t", "raw", "-q"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        print("realtime transcriber ready; speak. (~draft = instant, FINAL = GPU-corrected)",
              flush=True)

        utt = bytearray()
        muted = False
        try:
            while not self.stop:
                data = proc.stdout.read(READ_BYTES)
                if not data:
                    if proc.poll() is not None:
                        break
                    continue
                # Half-duplex: while the mute flag exists (Claude is speaking via
                # TTS), drain and discard mic audio so Claude's own voice never
                # reaches the screen.
                if MUTE_FLAG.exists():
                    muted = True
                    continue
                if muted:                     # just un-muted: drop any stale state
                    muted = False
                    rec.Reset()
                    utt = bytearray()
                    self.last_partial = ""
                    self.emitted = 0
                    continue
                utt.extend(data)
                if rec.AcceptWaveform(data):
                    # end of utterance (Vosk detected silence)
                    result = json.loads(rec.Result())
                    draft = result.get("text", "").strip()
                    if draft and is_filler_noise(draft):
                        draft = ""               # drop lone-filler noise entirely
                    if draft:
                        # emit any remaining words now finalized (incl. the last
                        # volatile one we held back during streaming)
                        toks = draft.split()
                        if len(toks) > self.emitted:
                            self.emit_words(toks[self.emitted:])
                        self.counter += 1
                        print(f"~draft[{self.counter}]> {draft}", flush=True)
                        # instant fast feed for the conversation loop (Vosk final,
                        # no waiting on the slower whisper pass)
                        with UTTERANCES_JSONL.open("a", encoding="utf-8") as h:
                            h.write(json.dumps({"created_at": utc_now(), "text": draft},
                                               ensure_ascii=True) + "\n")
                        # whisper still corrects for the saved record (messages.jsonl)
                        clip = trim_to_speech(bytes(utt), result.get("result", []))
                        self.correct_q.put((self.counter, clip, draft))
                    utt = bytearray()
                    self.last_partial = ""
                    self.emitted = 0
                else:
                    partial = json.loads(rec.PartialResult()).get("partial", "").strip()
                    if partial and partial != self.last_partial:
                        self.last_partial = partial
                        # stream all but the last (volatile) word live as spoken;
                        # the trailing word can still revise, so hold it back
                        toks = partial.split()
                        stable = toks[:-1]
                        if len(stable) > self.emitted:
                            self.emit_words(stable[self.emitted:])
                            print(f"  ~ {' '.join(stable[self.emitted:])}", flush=True)
                            self.emitted = len(stable)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop = True
            proc.terminate()
            print("realtime transcriber stopped", flush=True)


if __name__ == "__main__":
    Transcriber().run()
