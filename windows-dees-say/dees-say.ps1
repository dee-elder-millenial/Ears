$ErrorActionPreference = "Stop"

$Voice = $env:DEES_SAY_VOICE
$Speed = $null
$Volume = $null
$ListVoices = $false
$ShowHelp = $false
$TextParts = New-Object System.Collections.Generic.List[string]

function Show-Usage {
@"
Usage:
  dees-say.ps1 [flags] "text to speak"

Common flags:
  -v, --voice NAME        Use an installed Windows voice by exact or partial name.
  -l, --list-voices      List installed Windows SAPI voices.
  -s, --speed 0..1       Normalized speed. 0 is slow, 0.5 is default, 1 is fast.

Compatibility flags:
  --volume VALUE         Volume. 0..1 is treated as a multiplier; 0..100 as percent.
  --local                Accepted for Linux dees-say compatibility.
  --stream, --both       Accepted but ignored; this Windows port speaks locally only.
  --stream-url URL       Accepted but ignored.
  --remote URL           Same as --stream-url.

Examples:
  dees-say.ps1 "hello Dee!"
  dees-say.ps1 --list-voices
  dees-say.ps1 -v Zira -s 0.75 "Build finished."
"@
}

function Need-Value([string]$Flag, [int]$Index, [string[]]$Items) {
    if ($Index + 1 -ge $Items.Count) {
        throw "dees-say: $Flag requires a value."
    }
    return $Items[$Index + 1]
}

$Items = [string[]]$args
for ($i = 0; $i -lt $Items.Count; $i++) {
    $Arg = $Items[$i]
    switch -Regex ($Arg) {
        '^(--help|-h)$' {
            $ShowHelp = $true
            continue
        }
        '^(--list-voices|-l)$' {
            $ListVoices = $true
            continue
        }
        '^(--voice|-v)$' {
            $Voice = Need-Value $Arg $i $Items
            $i++
            continue
        }
        '^--voice=.+$' {
            $Voice = $Arg.Substring("--voice=".Length)
            continue
        }
        '^(--speed|-s)$' {
            $Speed = [double](Need-Value $Arg $i $Items)
            $i++
            continue
        }
        '^--speed=.+$' {
            $Speed = [double]$Arg.Substring("--speed=".Length)
            continue
        }
        '^--volume$' {
            $Volume = [double](Need-Value $Arg $i $Items)
            $i++
            continue
        }
        '^--volume=.+$' {
            $Volume = [double]$Arg.Substring("--volume=".Length)
            continue
        }
        '^(--length-scale|--noise|--noise-scale|--rhythm|--noise-w-scale|--pause|--sentence-silence)$' {
            [void](Need-Value $Arg $i $Items)
            $i++
            continue
        }
        '^(--length-scale|--noise|--noise-scale|--rhythm|--noise-w-scale|--pause|--sentence-silence)=.+$' {
            continue
        }
        '^(--local|--stream|--both)$' {
            continue
        }
        '^(--stream-url|--remote)$' {
            [void](Need-Value $Arg $i $Items)
            $i++
            continue
        }
        '^(--stream-url|--remote)=.+$' {
            continue
        }
        '^--$' {
            for ($j = $i + 1; $j -lt $Items.Count; $j++) {
                $TextParts.Add($Items[$j])
            }
            $i = $Items.Count
            break
        }
        default {
            $TextParts.Add($Arg)
            continue
        }
    }
}

if ($ShowHelp) {
    Show-Usage
    exit 0
}

Add-Type -AssemblyName System.Speech
$Synth = New-Object System.Speech.Synthesis.SpeechSynthesizer

if ($ListVoices) {
    $Synth.GetInstalledVoices() | ForEach-Object {
        $Info = $_.VoiceInfo
        $Enabled = if ($_.Enabled) { "enabled" } else { "disabled" }
        "{0} [{1}] {2}" -f $Info.Name, $Info.Culture, $Enabled
    }
    exit 0
}

if ($Voice) {
    $Voices = @($Synth.GetInstalledVoices() | Where-Object { $_.Enabled })
    $Match = $Voices | Where-Object { $_.VoiceInfo.Name -ieq $Voice } | Select-Object -First 1
    if (-not $Match) {
        $Match = $Voices | Where-Object { $_.VoiceInfo.Name -like "*$Voice*" } | Select-Object -First 1
    }
    if (-not $Match) {
        $Known = ($Voices | ForEach-Object { $_.VoiceInfo.Name }) -join ", "
        throw "dees-say: Windows voice not found: $Voice. Installed voices: $Known"
    }
    $Synth.SelectVoice($Match.VoiceInfo.Name)
}

if ($null -ne $Speed) {
    if ($Speed -lt 0 -or $Speed -gt 1) {
        throw "dees-say: --speed must be between 0 and 1."
    }
    $Synth.Rate = [int][Math]::Round(($Speed - 0.5) * 20)
}

if ($null -ne $Volume) {
    if ($Volume -le 1) {
        $Synth.Volume = [int][Math]::Round([Math]::Max(0, [Math]::Min(1, $Volume)) * 100)
    } else {
        $Synth.Volume = [int][Math]::Round([Math]::Max(0, [Math]::Min(100, $Volume)))
    }
}

$Text = ($TextParts -join " ").Trim()
if (-not $Text) {
    $Text = "Ladybug is online."
}

$Synth.Speak($Text)
