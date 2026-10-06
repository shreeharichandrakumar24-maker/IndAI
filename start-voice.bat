@echo off
setlocal
title IndAI Voice Agent
cd /d "%~dp0"

echo Starting IndAI Voice Agent...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-voice.ps1" %*

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Voice agent exited with error code %ERRORLEVEL%.
    pause
)
