@echo off
wsl.exe -d Ubuntu-24.04 --cd "%~dp0." --exec bash ./launch.sh
if errorlevel 1 pause
