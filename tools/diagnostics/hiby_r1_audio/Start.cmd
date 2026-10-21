@echo off
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Audio-diagnostics.ps1" %*
if errorlevel 1 pause
