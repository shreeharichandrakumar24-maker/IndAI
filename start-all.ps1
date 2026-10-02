# IndAI full dev stack: backend + website + simulator, one window each.
# 1) Run this file. 2) Website: http://localhost:5173  3) Simulator: http://localhost:5174
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Start-Process powershell -ArgumentList '-NoExit', '-Command', "& '$root\start-backend.ps1'"
Start-Sleep -Seconds 2
Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location '$root\frontend'; npm run dev"
Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location '$root\iot_simulator\frontend'; npm run dev"
Write-Output 'Launched 3 terminals: backend :8000, website :5173, old simulator :5174 (reference only).'
