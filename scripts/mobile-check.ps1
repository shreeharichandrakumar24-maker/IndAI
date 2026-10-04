# IndAI Mobile Connectivity Diagnostic Script
# Tests whether the backend is listening and reachable on the laptop's LAN IP address.
# Usage:
#   .\scripts\mobile-check.ps1
#   .\scripts\mobile-check.ps1 -Ip 192.168.1.4

param(
    [string]$Ip = ""
)

$ErrorActionPreference = 'SilentlyContinue'

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "IndAI Mobile Connectivity Check" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# 1. Check if backend is listening on port 8000
$conn = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }
if (-not $conn) {
    Write-Host "[FAIL] No process is listening on port 8000." -ForegroundColor Red
    Write-Host "Please start the backend first by running:" -ForegroundColor Yellow
    Write-Host "  .\start-backend.ps1" -ForegroundColor Yellow
    exit 1
}

$boundIp = $conn.LocalAddress | Select-Object -First 1
Write-Host "[OK] Backend process (PID $($conn.OwningProcess | Select-Object -First 1)) is listening on $boundIp:8000" -ForegroundColor Green
if ($boundIp -ne '0.0.0.0') {
    Write-Host "[WARNING] Backend is bound to $boundIp instead of 0.0.0.0. It will NOT accept connections from external devices." -ForegroundColor Red
    Write-Host "Ensure uvicorn is started with --host 0.0.0.0." -ForegroundColor Yellow
}

# 2. Identify candidate LAN IPs to test
$testIps = @()
if ($Ip -and $Ip.Trim().Length -gt 0) {
    $testIps += $Ip.Trim()
} else {
    $found = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object {
        $_.InterfaceAlias -notmatch 'Loopback|vEthernet|WSL|Virtual|Default Switch' -and
        $_.IPAddress -notmatch '^(127\.|169\.254\.)'
    } | Select-Object -ExpandProperty IPAddress
    if ($found) {
        $testIps += $found
    }
    # Always include 127.0.0.1 as baseline
    $testIps += "127.0.0.1"
}

Write-Host ""
Write-Host "Testing HTTP health endpoint on detected addresses..." -ForegroundColor Cyan

$allPassed = $true
foreach ($targetIp in $testIps) {
    $url = "http://$($targetIp):8000/api/health"
    Write-Host -NoNewline "Testing $url ... "
    try {
        $res = Invoke-RestMethod -Uri $url -Method Get -TimeoutSec 5 -ErrorAction Stop
        if ($res.status -eq 'ok' -or ($res -is [string] -and $res -match 'ok')) {
            Write-Host "PASS [status: ok]" -ForegroundColor Green
        } else {
            Write-Host "PASS [HTTP 200]" -ForegroundColor Green
        }
    } catch {
        Write-Host "FAIL" -ForegroundColor Red
        Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor DarkRed
        $allPassed = $false
    }
}

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
if ($allPassed) {
    Write-Host "SUMMARY: Backend is reachable locally and across LAN interfaces!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Steps to connect from your phone:" -ForegroundColor Yellow
    Write-Host "1. Connect phone to the SAME Wi-Fi network as this laptop."
    foreach ($targetIp in $testIps) {
        if ($targetIp -ne '127.0.0.1') {
            Write-Host "2. Open phone browser and test: http://$($targetIp):8000/api/health"
            Write-Host "3. In IndAI mobile app -> Server settings, set address to: http://$($targetIp):8000"
        }
    }
    Write-Host "4. If phone browser cannot reach the URL, run as Administrator:"
    Write-Host "   powershell -ExecutionPolicy Bypass -File .\scripts\allow-backend-firewall.ps1"
} else {
    Write-Host "SUMMARY: One or more endpoints failed." -ForegroundColor Red
    Write-Host "Troubleshooting checklist:" -ForegroundColor Yellow
    Write-Host "• Ensure uvicorn is running: .\start-backend.ps1"
    Write-Host "• Allow Windows Firewall inbound port 8000: .\scripts\allow-backend-firewall.ps1 (Run as Admin)"
    Write-Host "• Check if a VPN is interfering with LAN traffic"
}
Write-Host "==================================================" -ForegroundColor Cyan
