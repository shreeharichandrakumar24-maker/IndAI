# IndAI stop-all: frees ports 8000/5173/5174. Run it, then close the
# service windows by hand (they stay open showing terminated output).
$ports = @(8000, 5173, 5174)
foreach ($p in $ports) {
  $owners = Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue |
    Where-Object { $_.State -eq 'Listen' } |
    Select-Object -ExpandProperty OwningProcess -Unique
  foreach ($id in $owners) {
    try {
      $proc = Get-Process -Id $id -ErrorAction Stop
      Write-Output "Stopping $($proc.ProcessName) (PID $id) on port $p"
      Stop-Process -Id $id -Force
    } catch {
      Write-Output "PID $id already gone."
    }
  }
}
Write-Output 'Done. Ports 8000/5173/5174 should now be free.'
