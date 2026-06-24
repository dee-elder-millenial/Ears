# Ears realtime — dual-engine near-real-time transcription

Two passes on two different compute units, so they run in parallel:

- **Pass 1 — draft (instant, CPU):** Vosk streaming recognizer emits provisional
  words ~instantly as you speak.
- **Pass 2 — correction (GPU):** whisper.cpp on the AMD RX 580 via Vulkan
  re-transcribes each finished utterance and replaces the draft with an accurate line.

Latency/accuracy are decoupled: the instant feel comes from Pass 1; Pass 2 can use a
bigger model for accuracy without hurting that feel (the draft already painted the screen).

## Run

```bash
/cloud-mirror/Ears/realtime/start-realtime.sh          # starts under the render group
tail -F /cloud-mirror/Ears/realtime/logs/realtime.log  # watch (or via ssh from a Mac)
```

Stop: `kill "$(cat /cloud-mirror/Ears/realtime/realtime.pid)"`

The wrapper launches the program with `sg render -c …` so the whisper subprocess can
reach the GPU. It refuses to start if another process holds the mic (`pcmC3D0c`).

## Log format

```
  ~ friends romans country          # live Vosk partials (instant, as you speak)
~draft[2]> ... i come to bury ...    # Vosk draft when you pause (id in brackets)
FINAL[2]> Then ... bury Caesar ...   # GPU-corrected line  [model, Nms]
```

`FINAL[n]` correlates with `~draft[n]`. Corrected lines are also written to
`/cloud-mirror/Ears/transcripts/messages.jsonl` (same schema the voice router consumes,
with `source:"realtime"`, `engine`, `correction_ms`, `draft_text`).

## How it works / key fixes

- **Capture:** single `arecord` reader on `plughw:CARD=CODEC,DEV=0` (16 kHz mono).
- **Speech trimming (important):** whisper hallucinates filler ("come on, come on…") on
  silent audio. We use Vosk per-word timestamps (`SetWords(True)`) to slice each utterance
  to just the spoken span (`trim_to_speech`) before sending it to whisper. Without this,
  a one-word utterance sitting in 5 s of silence produced hallucinated phrases.
- **Correction worker:** a background thread runs whisper.cpp per utterance so live capture
  never blocks.

## Tuning (env vars)

| var | default | effect |
|-----|---------|--------|
| `WHISPER_MODEL` | `models/ggml-medium.en.bin` | correction model with best quality on the RX 580; set to `ggml-small.en.bin` for faster turns, `ggml-base.en.bin` for quickest (~450 ms) |
| `WHISPER_THREADS` | `4` | CPU threads for whisper's non-GPU ops |
| `PROMPT_BIAS` | `0` | feed the Vosk draft to whisper as `--prompt`. Off because the small Vosk drafts are too garbled to be a good prompt; revisit with a stronger draft model |
| `VOSK_MODEL` | `vosk-model-en-us-0.22` | draft model; fallback `vosk-model-small-en-us-0.15` for lighter/lower latency |
| `EARS_RT_KEEP_WAV` | `0` | keep per-utterance wavs in `/cloud-mirror/temp/ears-rt` for debugging |

## Benchmarks (Ryzen 5 1600 / RX 580, 10 s clip)

| model | device | total |
|-------|--------|-------|
| base.en | GPU (Vulkan) | ~0.40 s |
| base.en | CPU | ~2.9 s (≈7× slower) |
| small.en | GPU (Vulkan) | ~0.94 s |
| medium.en | GPU (Vulkan) | ~2–3 s |

## Requirements (already set up)

- `dee` is in the `render` group (GPU node access). whisper.cpp built with `-DGGML_VULKAN=1`.
- apt: `cmake pkg-config glslc libvulkan-dev vulkan-tools spirv-headers glslang-tools glslang-dev spirv-tools`.
- venv: `vosk` (in `/cloud-mirror/Ears/current-venv`).
- Models in `realtime/models/`: vosk small, `ggml-base.en.bin`, `ggml-small.en.bin`, `ggml-medium.en.bin`.
