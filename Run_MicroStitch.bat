@echo off
setlocal
cd /d "%~dp0"
python MicroStitch_Studio.py
if errorlevel 1 pause
