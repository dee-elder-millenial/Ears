from __future__ import annotations

"""Stream Claude's spoken words onto the HDMI display (claude track), paced to
roughly match speech, so they scroll like Dee's words but on the lower line in
Claude's color. Called by claude-say while dees-say is speaking."""

import json
import os
import sys
import time
from pathlib import Path

WORDS = Path("/cloud-mirror/Ears/realtime/logs/words.jsonl")
DELAY = float(os.environ.get("CLAUDE_WORD_DELAY", "0.33"))   # ~speech cadence per word


def main() -> None:
    text = " ".join(sys.argv[1:]).strip()
    for word in text.split():
        with WORDS.open("a", encoding="utf-8") as h:
            h.write(json.dumps({"role": "claude", "words": [[word, 1.0, 0]]},
                               ensure_ascii=True) + "\n")
        time.sleep(DELAY)


if __name__ == "__main__":
    main()
