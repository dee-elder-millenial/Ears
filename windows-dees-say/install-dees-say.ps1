$ErrorActionPreference = "Stop"

$InstallDir = Join-Path $env:USERPROFILE "bin"
$SourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path

New-Item -ItemType Directory -Force $InstallDir | Out-Null
Copy-Item -Force (Join-Path $SourceDir "dees-say.ps1") $InstallDir
Copy-Item -Force (Join-Path $SourceDir "dees-say.cmd") $InstallDir

$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$PathParts = @()
if ($UserPath) {
    $PathParts = $UserPath -split ';' | Where-Object { $_ }
}

$AlreadyPresent = $false
foreach ($Part in $PathParts) {
    if ($Part.TrimEnd('\') -ieq $InstallDir.TrimEnd('\')) {
        $AlreadyPresent = $true
        break
    }
}

if (-not $AlreadyPresent) {
    $NewPath = if ($UserPath) { "$UserPath;$InstallDir" } else { $InstallDir }
    [Environment]::SetEnvironmentVariable("Path", $NewPath, "User")
    $env:Path = "$env:Path;$InstallDir"
}

Write-Host "Installed dees-say to $InstallDir"
Write-Host "Test with:"
Write-Host "  dees-say.cmd `"hello Dee!`""
