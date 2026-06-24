from __future__ import annotations

"""Block until Dee's next finished utterance is transcribed, print it, exit.

Reads the whisper-corrected transcript (messages.jsonl) — the accurate version
of what Dee said — and waits for a new entry beyond what's already been seen.
Lets Claude monitor Ears turn-by-turn without busy-looping its own turns.

Usage: wait_for_utterance.py [--timeout SECONDS] [--reset]
Prints the new utterance text (empty output = timed out with nothing new).
"""

import argparse
import json
import time
from pathlib import Path

# Whisper-corrected feed (medium.en by default): clean text, much less "the" noise than
# raw Vosk. Set EARS_CONV_FEED=.../utterances.jsonl for the instant Vosk feed.
MESSAGES = Path(__import__("os").environ.get(
    "EARS_CONV_FEED", "/cloud-mirror/Ears/transcripts/messages.jsonl"))
STATE = Path("/cloud-mirror/Ears/realtime/.conv_seen")


def line_count() -> int:
    if not MESSAGES.exists():
        return 0
    with MESSAGES.open("r", encoding="utf-8", errors="replace") as f:
        return sum(1 for _ in f)


def read_texts(start: int) -> tuple[list[str], int]:
    texts: list[str] = []
    n = 0
    if not MESSAGES.exists():
        return texts, 0
    with MESSAGES.open("r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            n = i + 1
            if i < start:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = (rec.get("text") or "").strip()
            if t:
                texts.append(t)
    return texts, n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--reset", action="store_true", help="re-baseline to current end")
    args = ap.parse_args()

    if args.reset or not STATE.exists():
        STATE.write_text(str(line_count()), encoding="utf-8")

    try:
        seen = int(STATE.read_text(encoding="utf-8").strip())
    except (ValueError, FileNotFoundError):
        seen = line_count()

    SETTLE = 0.9        # after first new line, collect follow-on segments
    EXTRA = 4.0         # keep gathering this long while the thought is still tiny
    MIN_WORDS = 3       # below this it's probably a fragment; wait for more
    FILLER = {"the", "a", "an", "and", "um", "uh", "so", "i", "you", "it", "to", "of"}

    def gather() -> tuple[str, int]:
        texts, total = read_texts(seen)
        out: list[str] = []
        for t in texts:                                  # dedupe consecutive repeats
            if not out or out[-1].lower() != t.lower():
                out.append(t)
        return " ".join(out), total

    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        texts, _ = read_texts(seen)
        if texts:
            time.sleep(SETTLE)
            joined, total = gather()
            stop = time.monotonic() + EXTRA
            while len(joined.split()) < MIN_WORDS and time.monotonic() < stop:
                time.sleep(0.4)
                joined, total = gather()
            words = joined.split()
            # ignore a lone filler word (Vosk noise/fragment): re-baseline and keep waiting
            if len(words) <= 1 and joined.lower().strip(" .,?!") in FILLER:
                seen = total
                STATE.write_text(str(total), encoding="utf-8")
                continue
            STATE.write_text(str(total), encoding="utf-8")
            print(joined)
            return
        time.sleep(0.3)
    # timed out: print nothing


if __name__ == "__main__":
    main()
