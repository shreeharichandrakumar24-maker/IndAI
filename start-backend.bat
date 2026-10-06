@echo off
setlocal
title IndAI Backend (:8000)
cd /d "%~dp0"

echo Starting IndAI Backend...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-backend.ps1" %*

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Backend exited with error code %ERRORLEVEL%.
    pause
)
