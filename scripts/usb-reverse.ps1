# IndAI USB Port Forwarding Helper (ADB Reverse)
# Forwards port 8000 from a connected Android phone over USB to the laptop.
# Usage:
#   .\scripts\usb-reverse.ps1

$ErrorActionPreference = 'SilentlyContinue'

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "IndAI USB Port Forwarding (ADB Reverse)" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# 1. Check if adb is installed and in PATH
$adb = Get-Command adb -ErrorAction SilentlyContinue
if (-not $adb) {
    Write-Host "[ERROR] 'adb' was not found in your PATH." -ForegroundColor Red
    Write-Host "Ensure Android SDK platform-tools is installed and added to PATH." -ForegroundColor Yellow
    Write-Host "Alternative: Use Wi-Fi mode with the laptop's LAN IP instead of USB." -ForegroundColor Yellow
    exit 1
}

Write-Host "[OK] Found ADB: $($adb.Source)" -ForegroundColor Green

# 2. Check for connected Android devices
$devices = &(Get-Command adb).Source devices | Out-String
Write-Host ""
Write-Host "Connected devices:"
Write-Host $devices

$hasDevice = ($devices -split "`r?`n") | Where-Object { $_ -match "\bdevice$" }
if (-not $hasDevice) {
    Write-Host "[WARNING] No authorized Android device found in 'device' state." -ForegroundColor Yellow
    Write-Host "Please connect your phone via USB, enable 'USB Debugging' in Developer Options, and accept the prompt on the phone." -ForegroundColor Yellow
}

# 3. Execute adb reverse
Write-Host "Running: adb reverse tcp:8000 tcp:8000 ..." -ForegroundColor Cyan
$reverseOutput = & $adb.Source reverse tcp:8000 tcp:8000 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "[SUCCESS] Port 8000 successfully forwarded over USB!" -ForegroundColor Green
    Write-Host ""
    Write-Host "In the IndAI mobile app:" -ForegroundColor Yellow
    Write-Host "1. Tap 'Server settings' (or the gear icon)." -ForegroundColor Yellow
    Write-Host "2. Tap the 'USB (127.0.0.1)' chip (or type: http://127.0.0.1:8000)." -ForegroundColor Yellow
    Write-Host "3. Tap 'Test connection' to confirm reachability, then tap 'Save'." -ForegroundColor Yellow
    Write-Host "4. Log in normally." -ForegroundColor Yellow
} else {
    Write-Host "[FAIL] adb reverse failed: $reverseOutput" -ForegroundColor Red
}

Write-Host "==================================================" -ForegroundColor Cyan
