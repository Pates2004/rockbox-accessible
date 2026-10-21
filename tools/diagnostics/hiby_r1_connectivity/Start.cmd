@echo off
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Connectivity-diagnostics.ps1" -Menu %*
pause
