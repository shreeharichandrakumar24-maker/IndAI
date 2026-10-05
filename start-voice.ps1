# IndAI voice agent starter (own window). Uses the existing Jarvis venv
# python exactly as docs/VOICE_AGENT.md describes. Never prints secrets.
# If the voice agent cannot start, other services are unaffected.
# NOTE: if you edited backend/.env, restart the backend first (uvicorn does
# not always reload .env): .\stop-all.ps1, then .\start-all.ps1.
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Output '[voice] checking backend/.env ...'
$beFile = Join-Path $root 'backend\.env'
$beNames = @('LIVEKIT_URL', 'LIVEKIT_API_KEY', 'LIVEKIT_API_SECRET')
if (Test-Path -LiteralPath $beFile) {
  $beContent = Get-Content -LiteralPath $beFile
  $beMissing = @($beNames | Where-Object {
    $n = $_; -not ($beContent | Where-Object { $_ -match "^$n\s*=\s*\S" })
  })
  if ($beMissing.Count -gt 0) {
    Write-Output ('[voice] backend/.env missing: ' + ($beMissing -join ', ') + ' (names only) - token endpoint will 503.')
  } else {
    Write-Output '[voice] backend/.env LIVEKIT_* names present.'
  }
} else {
  Write-Output '[voice] backend/.env not found - token endpoint will 503.'
}
$envFile = Join-Path $root 'Jarvis\.env.local'
$venvPy = Join-Path $root 'Jarvis\venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $envFile)) {
  Write-Output 'Voice agent NOT started: Jarvis\.env.local is missing.'
  Write-Output 'Copy Jarvis\.env.example to Jarvis\.env.local and fill in'
  Write-Output 'LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET (names only shown here).'
  exit 1
}
$names = @('LIVEKIT_URL', 'LIVEKIT_API_KEY', 'LIVEKIT_API_SECRET')
$content = Get-Content -LiteralPath $envFile
$missing = @()
foreach ($n in $names) {
  $ok = $false
  foreach ($line in $content) {
    if ($line -match "^$n\s*=\s*\S") { $ok = $true }
  }
  if (-not $ok) { $missing += $n }
}
if ($missing.Count -gt 0) {
  Write-Output ('Voice agent NOT started: ' + ($missing -join ', ') + ' missing or empty in Jarvis\.env.local (names only).')
  exit 1
}
if (-not (Test-Path -LiteralPath $venvPy)) {
  Write-Output 'Voice agent NOT started: Jarvis venv python not found.'
  exit 1
}
# Kill any previous Jarvis agent process (identified by its own command
# line) so two agents never share a room and swallow each other's turns.
# Nothing else is touched: only python processes running Jarvis agent.py.
try {
  $stale = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -like '*Jarvis*agent.py*' }
  foreach ($p in $stale) {
    Write-Output ('[voice] stopping previous Jarvis agent (PID ' + $p.ProcessId + ') ...')
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
  }
} catch {
  Write-Output '[voice] (could not check for previous agent processes; continuing)'
}
Set-Location (Join-Path $root 'Jarvis')
Write-Output 'Starting IndAI voice agent (Ctrl+C stops it)...'
& $venvPy src\agent.py dev
