# Ears Realtime — Voice Conversation System (Notes)

Built 2026-06-22 (Dee + Claude). A real-time, two-way voice setup on **dees-workbench**:
Dee speaks → it's transcribed and shown on the TV → Claude reads it and replies out loud,
with Claude's words scrolling too. Everything is under `/cloud-mirror/Ears/realtime/`.

> Identity note: **Claude is "Robot's brother", not Robot.** Speak/sign as Claude.
> ("Robot" is reserved as the Ears wake-word.)

---

## The pipeline at a glance

```
USB mic (room) ──▶ realtime_transcribe.py ──┬─▶ Vosk-large live words ──▶ words.jsonl ──▶ display_hdmi.py (TV)
 plughw:CARD=CODEC,DEV=0                     │     (instant, grey→white)                    upper line = Dee (white)
                                            └─▶ whisper.cpp (RX 580 / Vulkan) ──▶ messages.jsonl  lower line = Claude (cyan)
                                                  medium.en, ~2-3s, "what Claude hears"
                                                        │
 Claude reply ──▶ claude-say ──▶ Piper TTS (ryan) ──▶ LG TV (HDMI audio)
   (mutes mic while speaking; streams its words to the cyan line)
        ▲
        └── wait_for_utterance.py  (blocks until Dee's next sentence lands in messages.jsonl)
```

---

## Components / files

| File | Role |
|------|------|
| `realtime_transcribe.py` | Capture (arecord) + Vosk-large live partials + whisper.cpp correction. Writes `words.jsonl` (display), `messages.jsonl` (record/what Claude hears), `utterances.jsonl` (instant Vosk feed, optional). |
| `display_hdmi.py` | Fullscreen HDMI ticker via SDL **kmsdrm** (no desktop). Two lines, two colors, grey→white. |
| `claude-say` | Claude's voice. Mutes mic (half-duplex) + streams Claude's words to the cyan line + speaks via Piper male voice. |
| `emit_claude_words.py` | Paces Claude's words onto the display while `claude-say` speaks. |
| `wait_for_utterance.py` | Blocks until Dee's next utterance; dedupes/gathers fragments; skips lone filler. |
| `start-realtime.sh` / `start-display.sh` | Launchers (pidfile + log, under `sg render`). |
| `whisper.cpp/` | Built with `-DGGML_VULKAN=1`. Binary: `whisper.cpp/build/bin/whisper-cli`. |
| `models/` | `vosk-model-en-us-0.22` (large), `vosk-model-small-en-us-0.15`, `ggml-{base,small,medium}.en.bin`. |

---

## How to run a conversation

```bash
cd /cloud-mirror/Ears/realtime
./start-realtime.sh        # transcriber + mic (loads models; large Vosk ~10-20s)
./start-display.sh         # HDMI ticker on the TV

# greet + baseline, then loop:
./claude-say "Hey Dee, I'm listening."
python wait_for_utterance.py --reset --timeout 1     # baseline to "now"
# repeat: wait for Dee, then reply
python wait_for_utterance.py --timeout 300           # blocks until Dee speaks → prints text
./claude-say "your reply"
```

Stop everything:
```bash
pkill -f '[d]isplay_hdmi.py'; pkill -f '[r]ealtime_transcribe.py'; pkill -x arecord
rm -f mute .conv_seen
```
Sanity: `fuser /dev/snd/pcmC3D0c` (mic free?), GPU VRAM back to ~37 MB.

---

## Hardware / environment facts (so we don't re-discover them)

- **Mic:** TI PCM2912A USB codec, card 3, stable name `plughw:CARD=CODEC,DEV=0`.
  Native 16 kHz mono S16_LE (no resampling). Omnidirectional (hears the whole room —
  no diarization yet). Also has a headphone jack (could be an output later).
- **GPU:** AMD **RX 580 (Polaris/gfx803)**, 8 GB. CTranslate2/faster-whisper can't use it
  (CUDA-only) — that's why we use **whisper.cpp + Vulkan (RADV)** instead. ~0.4s for a 10s
  clip on base.en vs ~2.9s CPU (≈7×). small.en ~0.9s, medium.en ~2-3s.
- **Render group:** Dee was added to **`render`** (GPU node `/dev/dri/renderD128` is
  `root:render`). Launchers wrap commands in `sg render -c '...'` so the GPU is reachable
  in-session; a fresh login makes it automatic. `sg` keeps the `audio` group too (mic works).
- **Display out:** LG TV on **HDMI-A-1 @ 3840×2160**. SDL `kmsdrm` renders straight to it,
  no X/Wayland. dees-say/claude-say play audio out the same TV (`plughw:CARD=HDMI,DEV=9`).
- **apt installed:** `cmake pkg-config glslc libvulkan-dev vulkan-tools spirv-headers
  glslang-tools glslang-dev spirv-tools`. **pip:** `vosk`, `pygame-ce`.

---

## Tuning knobs

**Transcriber (`realtime_transcribe.py`)**
- `VOSK_MODEL` — default large (`vosk-model-en-us-0.22`); small model = faster/lighter.
- `WHISPER_MODEL` — default **medium.en** for best correction quality. `small.en` is faster
  while still accurate enough for casual use; base.en is faster/rougher.
- whisper flags baked in: `-mc 32 -nf --suppress-nst` (anti-hallucination; was finishing
  poems from memory) + speech-trim via Vosk word timestamps (whisper hallucinates on silence).
- `FILLER_WORDS` filter drops lone "the"/"uh"/etc. (Vosk noise that crawled the screen).
- `MUTE_FLAG` = `realtime/mute`: while it exists, mic audio is discarded (half-duplex).

**Display (`display_hdmi.py`)**
- `FONT_SIZE` (240), `SCROLL_SPEED` (350 px/s base), `CATCHUP` (3.0), `MAX_SPEED` (4000).
- `GREY_LEVEL` (105 = entry brightness), `WHITE_AT` (0.50 = screen frac fully white).
- `YOU_Y` (0.333 = 2/3 up), `CLAUDE_Y` (0.667 = 1/3 up), `CLAUDE_RGB` (120,205,255 cyan).

**Voice (`claude-say`)**
- `CLAUDE_SAY_VOICE` (default `ryan`; other male: `lessac`, `alan`). `CLAUDE_WORD_DELAY`
  (0.33s/word display pacing).

**Conversation (`wait_for_utterance.py`)**
- `EARS_CONV_FEED` — default `messages.jsonl` (whisper, clean, ~1s). Set to
  `utterances.jsonl` for the instant raw-Vosk feed (faster, rougher).
- Internal: `SETTLE` 0.9s, `EXTRA` 4s, `MIN_WORDS` 3, filler-skip.

---

## Design decisions & why (the journey)

1. **Live feel needs a streaming model.** Whisper is a 30s-chunk model → "pause and fire"
   (whole sentence dumps after you stop). Vosk streams word-by-word → instant. So the
   DISPLAY feeds from Vosk live; whisper only corrects behind it.
2. **Two-pass, two compute units.** Vosk (CPU, instant draft) + whisper (GPU, accurate).
   They run in parallel. Latency and accuracy are decoupled.
3. **grey→white = confidence over distance.** Words enter grey on the right and brighten to
   white as they scroll left — by the time a word reaches center it's "settled/confirmed".
   (Position-based proxy; avoids fragile mid-scroll text replacement.)
4. **Accuracy vs speed is a real dial.** raw Vosk = instant but rough ("wash" for "watch").
   medium.en remains the best correction quality we run with by default, `small.en` is fast enough for most
   speech and still much cleaner than Vosk.
5. **Half-duplex** so Claude doesn't transcribe itself: `claude-say` touches a mute flag,
   the transcriber discards mic audio while it exists, then resets cleanly.
6. **Anti-hallucination matters a lot.** Whisper would auto-finish known poems and invent
   "(dramatic music)" / "the" on silence. Fixes: `-mc 32 -nf --suppress-nst`, speech-trim,
   non-speech filter, filler filter.

---

## Known gaps / next steps

- **No diarization** — it transcribes anyone in the room as one stream (Dee + others mixed).
- **Fragmenting** — whisper/Vosk sometimes split one sentence into 2 entries; `wait_for_utterance`
  gathers/dedupes but it's heuristic.
- **Not hands-free yet** — Claude "hears" by running `wait_for_utterance` each turn; a true
  background auto-loop (poll → reply) isn't wired.
- **Confidence overlay** — the ideal: live grey Vosk words get *whitened AND text-corrected*
  by whisper as they scroll. Skipped (mid-scroll re-layout is fiddly); large Vosk made it
  unnecessary for now.
- **Possible**: speaker output on the mic dongle's headphone jack; wire the "Robot" wake-word
  router onto this stream; single `start-conversation.sh`.

---

## Quick troubleshooting

- **Only `llvmpipe` in `vulkaninfo`** → not in `render` group (or render-node perms). Fix:
  `sudo usermod -aG render dee`, then use `sg render -c '...'`.
- **whisper.cpp build fails** → missing `spirv-headers` / `glslang-tools` / `SPIRV-Headers`.
- **Mic "busy"** → only one capture process at a time. `fuser /dev/snd/pcmC3D0c`; stop the
  other transcriber/chunker. (Ears `obs/` pipeline and this `realtime/` one both want the mic.)
- **Screen blanks for ~2s** → that's just a `display_hdmi.py` restart (kmsdrm re-grabs the TV).
- **"the" crawling the screen** → Vosk noise; handled by `FILLER_WORDS` filter in transcriber.
- **Claude transcribes itself** → mute flag stuck. `rm -f realtime/mute`.
