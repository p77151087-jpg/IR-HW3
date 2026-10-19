@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop_background_hw3.ps1"
if errorlevel 1 pause
