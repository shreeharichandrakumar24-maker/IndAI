// Badge tones for machine status / health values. Pure helpers shared by
// the fleet table, details modal and telemetry views.
export function toneForMachineStatus(status) {
  const s = (status || '').toUpperCase();
  if (s === 'OPERATIONAL' || s === 'RUNNING') return 'ok';
  if (s === 'IDLE') return 'info';
  if (s === 'MAINTENANCE') return 'warn';
  if (s === 'STOPPED' || s === 'DOWN' || s === 'FAULT') return 'bad';
  return 'neutral';
}

export function toneForHealth(health) {
  const h = (health || '').toUpperCase();
  if (h === 'GOOD') return 'ok';
  if (h === 'WARNING' || h === 'DEGRADED' || h === 'FAIR') return 'warn';
  if (h === 'CRITICAL' || h === 'POOR' || h === 'DOWN') return 'bad';
  return 'neutral';
}
