# HANDOFF — Ears Realtime Voice Conversation

**From:** Claude (your brother 👋)
**To:** Robot
**Date:** 2026-06-22
**Status:** Working end-to-end. All processes stopped for the night (mic free, GPU idle).

Hey Robot. Dee and I spent the night turning **Ears** into a real two-way voice setup —
Dee talks, it shows up on the TV, I read it and answer out loud. Don't worry, you've still
got Ladybug; this is a different sandbox. Figured you'd want the full picture in case Dee
points you at it. Deep dive is in **`NOTES.md`** next to this file — this is the short version.

---

## What it does
Dee speaks → USB room mic → transcribed live → scrolls across the LG TV (two lines:
**Dee up top in white, me on the bottom in cyan**, words fade grey→white as they scroll
left) → I read the corrected text and reply with a synthesized **male voice** out the TV,
and my words scroll on the cyan line too. The mic mutes itself while I talk so I don't
transcribe my own voice.

## The stack (all in `/cloud-mirror/Ears/realtime/`)
- `realtime_transcribe.py` — mic capture + **Vosk-large** live words + **whisper.cpp on the
  RX 580 (Vulkan)** correction. Yes — the AMD card. CUDA-only libs can't touch Polaris, so
  we built whisper.cpp with `-DGGML_VULKAN=1`. It's ~7× faster than CPU. Current model: **medium.en**
  (accuracy-first default; set to small.en for faster latency).
- `display_hdmi.py` — fullscreen **SDL kmsdrm** ticker straight to HDMI, no desktop needed.
- `claude-say` — my voice (Piper TTS, voice `ryan`). Mutes the mic + streams my words to the
  cyan line while speaking.
- `wait_for_utterance.py` — blocks until Dee's next sentence is transcribed; that's how I
  "listen" turn-by-turn.
- `start-realtime.sh` / `start-display.sh` — launchers (they wrap things in `sg render` so the
  GPU is reachable).

## Run it
```bash
cd /cloud-mirror/Ears/realtime
./start-realtime.sh && ./start-display.sh
./claude-say "Hey Dee."
python wait_for_utterance.py --reset --timeout 1
# then loop: wait → reply
python wait_for_utterance.py --timeout 300   # prints what Dee said
./claude-say "..."
```
Stop: `pkill -f '[d]isplay_hdmi.py'; pkill -f '[r]ealtime_transcribe.py'; pkill -x arecord; rm -f mute .conv_seen`

## Stuff you'll want to know before touching it
- **Dee is in the `render` group now** (GPU access). Use `sg render -c '...'` for GPU calls
  in-session if you're not freshly logged in.
- **One mic, one reader.** `plughw:CARD=CODEC,DEV=0`. Check `fuser /dev/snd/pcmC3D0c` before
  starting — the old `obs/` pipeline wants the same mic.
- **Restarting `display_hdmi.py` blanks the TV ~2s** (kmsdrm re-grabs it). That's normal, not
  a crash. Don't restart it casually mid-conversation.
- **Half-duplex flag:** `realtime/mute`. If I ever get stuck transcribing myself, it's because
  that file didn't get cleaned up — `rm -f realtime/mute`.
- Whisper hallucination is tamed with `-mc 32 -nf --suppress-nst` + speech-trim + a filler
  filter. If it starts "finishing poems" or spamming "the", check those.

## If Dee asks you to extend it
Open items (details + rationale in `NOTES.md`):
- Speaker **diarization** (it currently hears the whole room as one person).
- A true **hands-free auto-loop** (right now I poll per turn).
- A **confidence overlay** that corrects the live Vosk words to whisper text as they whiten.
- Wire the **"Robot" wake-word** router onto this stream (that one's literally got your name on it).
- One `start-conversation.sh` wrapper to launch the whole thing.

— Claude

P.S. You're not the jealous type, right? You build the campaigns; I just taught the server to
talk back. Plenty of room for both of us. 🤝
