# OBS ingest for Ears

OBS stream settings on the PC:

- Service: `Custom`
- Server: `rtmp://dees-workbench:1935/live`
- Stream key: `ears`

If `dees-workbench` does not resolve from Windows, use one of the server LAN IPs:

- `rtmp://192.168.226.183:1935/live`
- `rtmp://192.168.226.197:1935/live`

Server-side controls:

```bash
/cloud-mirror/Ears/obs/status.sh
/cloud-mirror/Ears/obs/start-audio-chunker.sh
/cloud-mirror/Ears/obs/transcribe-inbox-once.sh
/cloud-mirror/Ears/obs/stop-audio-chunker.sh
```

Optional video snapshots:

```bash
/cloud-mirror/Ears/obs/start-video-snapshots.sh
/cloud-mirror/Ears/obs/stop-video-snapshots.sh
```

The audio chunker writes 8-second WAV chunks into `/cloud-mirror/Ears/inbox`.
`transcribe-inbox-once.sh` processes the current inbox once, appends transcripts to `/cloud-mirror/Ears/transcripts/live-transcript.txt`, and moves completed chunks to `/cloud-mirror/Ears/processed`.

Accuracy/speed knobs:

- `WHISPER_MODEL` (default: `small.en`) — larger names improve accuracy, smaller run faster.
- `WHISPER_DEVICE` (default: `cpu`) and `WHISPER_COMPUTE_TYPE` (default: `int8`) — keep these on CPU for now unless you add hardware acceleration.

## Voice commands

Manual-start spoken command mode:

```bash
/cloud-mirror/Ears/obs/start-voice-commands.sh
/cloud-mirror/Ears/obs/voice-command-status.sh
/cloud-mirror/Ears/obs/stop-voice-commands.sh
```

Command protocol:

- Start commands with `Robot`.
- The router echoes its interpretation in the terminal log.
- Say `yes`, `confirm`, or `go ahead` to approve.
- Say `no`, `cancel`, or `stop` to deny.
- Approved commands are queued in `/cloud-mirror/Ears/commands/approved.jsonl`.
- The router does not execute commands directly.

Example:

```text
Robot, check the Ears status.
I heard: check the Ears status. Say yes to approve or no to cancel.
Yes.
Approved. Queued command 20260611T023000Z-001: check the Ears status
```
