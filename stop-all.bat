@echo off
setlocal
title Stop IndAI Services
cd /d "%~dp0"

echo ========================================================
echo              Stopping IndAI Services
echo ========================================================
echo.
echo Freeing ports 8000, 5173, 5174...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-all.ps1" %*

echo.
pause
