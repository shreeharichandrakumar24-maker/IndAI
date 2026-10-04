# IndAI Backend Firewall Configuration Script
# MUST BE RUN MANUALLY AS ADMINISTRATOR IN POWERSHELL.
# Usage: Right-click PowerShell -> 'Run as Administrator', then execute:
#   powershell -ExecutionPolicy Bypass -File .\scripts\allow-backend-firewall.ps1

$ErrorActionPreference = 'Stop'

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "IndAI Backend Firewall Configuration" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# 1. Check for Administrator privileges
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[ERROR] This script requires Administrator privileges to manage Windows Firewall." -ForegroundColor Red
    Write-Host "Please open PowerShell as Administrator and run this script again:" -ForegroundColor Yellow
    Write-Host "  powershell -ExecutionPolicy Bypass -File `"$PSScriptRoot\allow-backend-firewall.ps1`"" -ForegroundColor Yellow
    exit 1
}

$ruleName = "IndAI Backend (Port 8000)"
$port = 8000

# 2. Check if rule already exists (idempotent)
$existingRule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if (-not $existingRule) {
    # Check legacy/alternative name as well
    $existingRule = Get-NetFirewallRule -DisplayName "IndAI 8000" -ErrorAction SilentlyContinue
}

if ($existingRule) {
    Write-Host "[INFO] Firewall rule already exists: $($existingRule.DisplayName)" -ForegroundColor Green
    Write-Host "Inbound TCP port $port is already allowed." -ForegroundColor Green
} else {
    Write-Host "[INFO] Creating inbound firewall rule for TCP port $port..." -ForegroundColor Yellow
    New-NetFirewallRule -DisplayName $ruleName `
                        -Direction Inbound `
                        -LocalPort $port `
                        -Protocol TCP `
                        -Action Allow `
                        -Profile Any `
                        -Description "Allow inbound TCP traffic for IndAI FastAPI backend on port 8000" | Out-Null
    Write-Host "[SUCCESS] Created inbound firewall rule '$ruleName' allowing TCP port $port across all network profiles." -ForegroundColor Green
}

Write-Host ""
Write-Host "Next step:" -ForegroundColor Cyan
Write-Host "• Ensure your laptop and phone are connected to the same Wi-Fi network."
Write-Host "• Start the backend with .\start-backend.ps1"
Write-Host "• Verify access with .\scripts\mobile-check.ps1"
Write-Host "==================================================" -ForegroundColor Cyan
