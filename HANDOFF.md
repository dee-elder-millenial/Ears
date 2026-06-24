# Ears Handoff

Last updated: 2026-06-23T01:00:00Z
Machine: dees-workbench
State: Paused

> **NEWEST (2026-06-22, for Robot):** Ears now has a full **two-way voice conversation**
> system — Dee talks, it scrolls on the TV, Claude reads it and replies out loud (male
> voice), Claude's words scroll too. whisper.cpp runs on the **AMD RX 580 via Vulkan**.
> Everything is in `/cloud-mirror/Ears/realtime/` — see **`realtime/HANDOFF.md`** (written
> for you, Robot) and **`realtime/NOTES.md`** (full design notes). The sections below are
> the earlier OBS / Silero transcription work.

## Direct USB Mic + Silero VAD Near-Real-Time Transcription - 2026-06-22

A USB room mic was plugged directly into dees-workbench, making the server itself
the listening device — no OBS, RTMP, MediaMTX, or upstairs PC required. This is now
the preferred capture path.

### The mic

- Device: Texas Instruments PCM2912A USB audio codec (`lsusb` id `08bb:2912`).
- ALSA: card 3, referenced by the stable name `plughw:CARD=CODEC,DEV=0` (not `hw:3,0`,
  which can reshuffle on reboot/replug).
- Native format: mono S16_LE, 16 kHz — exactly what faster-whisper wants, no resampling.
- It also has a playback/headphone interface, so the same dongle could later be Robot's
  "mouth" (a `dees-say` output target), not just its ears.
- Caveat: high self-noise floor (~-25 dBFS) and it is omnidirectional — it picks up the
  whole room (e.g. other people talking). No speaker diarization yet; everything lands in
  one transcript stream. Diarization deferred.

### New files (added; nothing existing was modified)

- `obs/stream_transcribe.py` — PREFERRED. Near-real-time transcriber. Reads raw PCM from
  the mic via `arecord`, runs Silero neural VAD per 32 ms window for endpointing, and
  transcribes each utterance from memory (NumPy array, no file I/O) the moment the speaker
  pauses. Emits the same `transcripts/messages.jsonl` records as the file pipeline, so the
  voice router can consume them unchanged. Latency ≈ 0.7 s hangover + ~1 s compute ≈ under
  ~2 s after a pause. No noise-floor calibration needed — Silero judges speech spectrally,
  so the noisy mic floor is irrelevant, and silence-hallucinations are gone.
- `obs/start-mic-chunker.sh` — ALSA-input twin of `start-audio-chunker.sh` (8 s WAV segments
  to `inbox/` from the mic instead of RTMP). Fixed-window fallback.
- `obs/live_transcribe.py` — resident-model file-based transcriber (loads `base.en` once
  instead of per-call like `transcribe_inbox_once.py`). Pairs with `start-mic-chunker.sh`.
  Superseded by `stream_transcribe.py` for latency; kept as a fallback.

### Run it

```bash
# preferred: near-real-time streaming transcriber (holds the mic via arecord)
/cloud-mirror/Ears/current-venv/bin/python /cloud-mirror/Ears/obs/stream_transcribe.py \
  >> /cloud-mirror/Ears/logs/stream-transcribe.log 2>&1 &
# watch live (from a Mac on the LAN):
ssh dee@192.168.226.183 'tail -n 0 -F /cloud-mirror/Ears/logs/stream-transcribe.log'
```

Log line format: `[<UTC>] (<compute>s,<reason>)  <text>` — the `(0.96s,pause)` is the whisper
compute time for that utterance; add the ~0.7 s hangover for end-to-end latency.

NOTE: the mic is a single-capture device — only one reader at a time. Stop the ffmpeg
chunker before starting the `arecord`-based streamer (and vice versa), or ALSA will conflict.
Free check: `fuser /dev/snd/pcmC3D0c`.

### Tuning knobs (env vars on stream_transcribe.py)

- `VAD_THRESHOLD` (default 0.5) — Silero speech probability cutoff.
- `HANGOVER_MS` (700), `ATTACK_MS` (96), `PREROLL_MS` (320), `MAX_UTTERANCE_S` (12) — endpointing.
- `beam_size` is hardcoded to 5; drop to 1 in the script for faster (slightly less accurate) decode.

### Next on this path

- Optional `start-stream-transcribe.sh` / `stop-` wrapper with pidfile + log, to match the
  other Ears component scripts (currently started by hand).
- Speaker diarization (e.g. pyannote, or speaker-embedding clustering) if "who is talking"
  ever matters for the wake-word router — currently anyone in earshot would be transcribed.
- Wire the wake-word voice router (`voice_router.py`) onto this stream; VAD utterance
  boundaries should make "Robot, ..." detection more reliable than fixed 8 s chunks.

## Windows dees-say Port - 2026-06-21

Dee wanted a lightweight way for Robot/Codex to make sound on SBE-Lenovo without restarting the full Ears OBS/audio-command stack. A Windows `dees-say` port was staged here:

```text
/srv/cloud-mirror/Ears/windows-dees-say/
```

Files:

- `dees-say.ps1` - PowerShell/SAPI speech implementation.
- `dees-say.cmd` - cmd.exe shim so Windows can run `dees-say.cmd "hello Dee!"`.
- `install-dees-say.ps1` - copies both files to `%USERPROFILE%\bin` and adds that folder to the user PATH.
- `README.md` - install and remote command examples.

This is not a Piper port. It uses built-in Windows SAPI voices, which is exactly the point for the current use case: no Python, no ffmpeg, no OBS, no audio routing, no extra packages.

Supported useful flags:

```powershell
dees-say.cmd "hello Dee!"
dees-say.cmd --list-voices
dees-say.cmd --voice Zira -s 0.8 "Build finished."
```

Compatibility notes:

- `--voice`, `--speed`, `--volume`, and `--list-voices` work.
- `--stream`, `--both`, `--local`, `--stream-url`, and Piper tuning flags are accepted so Linux-style commands do not crash, but only local Windows speaker output is implemented.

Install on SBE-Lenovo from the mirrored folder:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-dees-say.ps1
dees-say.cmd "hello Dee!"
```

Intended remote shape once SSH is reachable:

```bash
ssh SBE-Lenovo.local 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\bin\dees-say.ps1" "hello Dee!"'
```

Current network note:

- `SBE-Lenovo.local` resolved from dees-workbench to `192.168.226.192`.
- SSH to `SBE-Lenovo.local:22` timed out from dees-workbench during this setup, so the files were staged in the mirror but not installed remotely.

## Summary

Ears is a local OBS audio/video ingest and voice-command bridge for Codex running on dees-workbench. OBS streams from the upstairs PC to MediaMTX over RTMP, ffmpeg chunks audio into WAV files, faster-whisper transcribes chunks locally, and a voice router listens for commands beginning with `Robot`.

The current v1 command protocol is intentionally conservative. A spoken command must start with `Robot`; the router echoes its interpretation to the terminal/log and waits for spoken approval or denial. Approved commands are queued to JSONL but are not executed automatically.

## Current Components

There are now two capture paths:

- PREFERRED — Direct USB mic + Silero streaming: `/cloud-mirror/Ears/obs/stream_transcribe.py`
  (see the 2026-06-22 section above). No OBS/RTMP/MediaMTX needed.
- LEGACY — OBS/RTMP ingest (below), still intact for remote/upstairs-PC capture.

- Media ingest: Docker container `ears-mediamtx`, normally started on RTMP port `1935`.
- OBS target: `rtmp://dees-workbench:1935/live` with stream key `ears`.
- Audio chunking (RTMP): `/cloud-mirror/Ears/obs/start-audio-chunker.sh`.
- Audio chunking (USB mic): `/cloud-mirror/Ears/obs/start-mic-chunker.sh`.
- Manual transcription: `/cloud-mirror/Ears/obs/transcribe-inbox-once.sh`.
- Voice command session: `/cloud-mirror/Ears/obs/start-voice-commands.sh` and `/cloud-mirror/Ears/obs/stop-voice-commands.sh`.
- Terminal follow helper: `/cloud-mirror/Ears/obs/follow-voice-commands.sh`.
- Approved commands queue: `/cloud-mirror/Ears/commands/approved.jsonl`.

## Shutdown State

The voice-command router, transcriber watcher, audio chunker, video snapshotter, tmux follower, and MediaMTX container were shut down at the end of the session. If resuming tomorrow, start MediaMTX or recreate it before starting OBS tests.

## Recovery / Resume

### Direct USB mic (preferred, simplest)

1. Confirm the mic is present: `arecord -l` should list `card 3: CODEC` (PCM2912A).
2. Make sure no other process holds it: `fuser /dev/snd/pcmC3D0c` (should be empty).
3. Start the streamer (see "Run it" in the 2026-06-22 section).
4. Watch the log live, locally or via SSH from a Mac on the LAN.

### OBS/RTMP (legacy, for remote capture)

1. Start or verify MediaMTX.
2. Start OBS on the PC using the RTMP target above.
3. Run `/cloud-mirror/Ears/obs/start-voice-commands.sh`.
4. In a terminal, run `/cloud-mirror/Ears/obs/follow-voice-commands.sh` or attach a tmux session that tails the router log.
5. Test with: `Robot, check the Ears status.` then say `Yes`.

## Next Actions

- Make the terminal echo visible without needing a separate manual tail command.
- Add an operator command that drains `/cloud-mirror/Ears/commands/approved.jsonl` and presents approved commands to the active Codex session.
- Improve phrase grouping so short commands split across two chunks are joined more reliably.
- Add a cleanup/archive script for old processed WAV chunks.
- Consider a speaker output path later, but keep terminal echo as the v1 confirmation surface.
