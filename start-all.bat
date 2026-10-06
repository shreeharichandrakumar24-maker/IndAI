@echo off
setlocal
title IndAI Starter
cd /d "%~dp0"

echo ========================================================
echo              IndAI Full Stack Launcher
echo ========================================================
if not exist "%~dp0frontend\node_modules" (
    echo [INFO] Installing frontend dependencies...
    pushd "%~dp0frontend" && call npm install && popd
)

if not exist "%~dp0iot_simulator\frontend\node_modules" (
    echo [INFO] Installing IoT simulator frontend dependencies...
    pushd "%~dp0iot_simulator\frontend" && call npm install && popd
)

echo Launching backend (:8000), frontend (:5173), simulator (:5174),
echo and voice agent (if configured)...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-all.ps1" %*

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Launcher exited with error code %ERRORLEVEL%.
    pause
)
