# IndAI backend starter (dedicated terminal).
# Kills any squatter on port 8000, then runs uvicorn in the foreground.
# Stop with Ctrl+C. Requires backend/.env with DATABASE_URL.
$ErrorActionPreference = 'SilentlyContinue'
$conn = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue |
  Where-Object { $_.State -eq 'Listen' }
if ($conn) {
  Write-Output "Port 8000 held by PID $($conn.OwningProcess) - stopping it..."
  Stop-Process -Id $conn.OwningProcess -Force
  Start-Sleep -Seconds 2
}
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)
Write-Output 'Starting IndAI backend on http://localhost:8000 (docs: /docs)...'
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
