@echo off
setlocal
title IndAI Starter
cd /d "%~dp0"

echo ========================================================
echo              IndAI Full Stack Launcher
echo ========================================================
echo.
echo Launching backend (:8000), frontend (:5173), simulator (:5174),
echo and voice agent (if configured)...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-all.ps1" %*

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Launcher exited with error code %ERRORLEVEL%.
    pause
)
