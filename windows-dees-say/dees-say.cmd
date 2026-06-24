@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0dees-say.ps1" %*
exit /b %ERRORLEVEL%
