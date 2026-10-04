# IndAI full dev stack: backend + website + simulator, one window each,
# plus the voice agent in its own window ONLY when configured.
# 1) Run this file. 2) Website: http://localhost:5173  3) Simulator: http://localhost:5174
# If you edited backend/.env, restart the backend afterwards (uvicorn does
# not always reload .env) - run .\stop-all.ps1, then this file again.
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Output '[1/3] backend :8000 ...'
Start-Process powershell -ArgumentList '-NoExit', '-Command', "& '$root\start-backend.ps1'"
Start-Sleep -Seconds 2
Write-Output '[2/3] website :5173 ...'
Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location '$root\frontend'; npm run dev"
Write-Output '[3/3] old simulator :5174 (reference only) ...'
Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location '$root\iot_simulator\frontend'; npm run dev"
Write-Output 'Launched 3 terminals: backend :8000, website :5173, old simulator :5174 (reference only).'
$lk = @('LIVEKIT_URL', 'LIVEKIT_API_KEY', 'LIVEKIT_API_SECRET')
$be = Join-Path $root 'backend\.env'
$je = Join-Path $root 'Jarvis\.env.local'
foreach ($pair in @(@('backend/.env', $be), @('Jarvis/.env.local', $je))) {
  $label, $path = $pair
  if (-not (Test-Path -LiteralPath $path)) {
    Write-Output "Voice: $label missing - voice agent will 503 (see .\start-voice.ps1)."
    continue
  }
  $content = Get-Content -LiteralPath $path
  $missing = @($lk | Where-Object {
    $n = $_; -not ($content | Where-Object { $_ -match "^$n\s*=\s*\S" })
  })
  if ($missing.Count -eq 0) {
    Write-Output "Voice: LIVEKIT_* names present in $label."
  } else {
    Write-Output ('Voice: ' + ($missing -join ', ') + ' missing in ' + $label + ' (names only). Run .\start-voice.ps1 for details.')
  }
}
# Option B: open the voice window only when Jarvis/.env.local has all three
# LIVEKIT_* names filled; otherwise print one skip line (no extra window).
$voiceReady = $false
if (Test-Path -LiteralPath $je) {
  $jeContent = Get-Content -LiteralPath $je
  $jeMissing = @($lk | Where-Object {
    $n = $_; -not ($jeContent | Where-Object { $_ -match "^$n\s*=\s*\S" })
  })
  $voiceReady = ($jeMissing.Count -eq 0)
}
if ($voiceReady) {
  Write-Output '[4/4] voice agent (keys present, opening its window) ...'
  Start-Process powershell -ArgumentList '-NoExit', '-Command', "& '$root\start-voice.ps1'"
} else {
  Write-Output 'Voice agent skipped (Jarvis/.env.local missing or incomplete). Run .\start-voice.ps1 once keys are added.'
}
