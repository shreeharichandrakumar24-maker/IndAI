@echo off
setlocal
title IndAI Apply Multi-Factory Migration
cd /d "%~dp0"

echo ========================================================
echo       Applying Multi-Factory Database Migration
echo ========================================================
echo.
python -m backend.scripts.apply_migration backend\db\migrations\008_multi_factory.sql %*

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Migration failed with error code %ERRORLEVEL%.
) else (
    echo.
    echo [SUCCESS] Migration completed successfully.
)
echo.
pause
