# Windows dees-say

Small Windows port of `dees-say` for SBE-Lenovo. It uses built-in Windows SAPI speech, so it does not need Piper, Python, ffmpeg, or audio routing.

## Files

- `dees-say.ps1` - PowerShell implementation.
- `dees-say.cmd` - cmd.exe shim so `dees-say.cmd "hello"` works.

## Local Test On Windows

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\dees-say.ps1 "hello Dee!"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\dees-say.ps1 --list-voices
.\dees-say.cmd -s 0.75 "Build finished."
```

## Suggested Install

Copy both files to a folder on SBE-Lenovo, for example:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-dees-say.ps1
```

The installer copies `dees-say.ps1` and `dees-say.cmd` to `%USERPROFILE%\bin` and adds that folder to the user PATH if needed.

## Remote SSH Shape

```bash
ssh SBE-Lenovo.local 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\bin\dees-say.ps1" "hello Dee!"'
```

The Windows port accepts common Linux `dees-say` flags:

```powershell
dees-say.cmd "hello Dee!"
dees-say.cmd --voice Zira -s 0.8 "hello Dee!"
dees-say.cmd --list-voices
```

`--stream`, `--both`, and Piper tuning flags are accepted for compatibility but ignored. This port speaks through the Windows default audio output only.
