// Deterministic telemetry display helpers. No anomaly scoring, no AI
// language — freshness is derived only from reading age, and the "live"
// threshold reflects the simulator's documented 10s transmit cadence.
export const POLL_INTERVAL_MS = 10000;
export const LIVE_AFTER_MS = 45000;
export const DELAYED_AFTER_MS = 5 * 60 * 1000;

export function toneForTelemetryStatus(status) {
  const s = (status || '').toUpperCase();
  if (s === 'RUNNING') return 'ok';
  if (s === 'IDLE') return 'info';
  if (s === 'MAINTENANCE') return 'warn';
  if (s === 'STOPPED' || s === 'FAULT') return 'bad';
  return 'neutral';
}

export function formatDateTime(value) {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString();
}

export function formatReading(value, digits = 1) {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  return Number.isNaN(n) ? '—' : n.toFixed(digits);
}

// Freshness of one telemetry row based purely on its timestamp age.
// Returns { key, label, tone } for badge rendering.
export function freshnessOf(timestamp, now = Date.now()) {
  if (!timestamp) return { key: 'none', label: 'NO DATA', tone: 'neutral' };
  const age = now - new Date(timestamp).getTime();
  if (Number.isNaN(age)) return { key: 'none', label: 'NO DATA', tone: 'neutral' };
  if (age <= LIVE_AFTER_MS) return { key: 'live', label: 'LIVE', tone: 'ok' };
  if (age <= DELAYED_AFTER_MS) return { key: 'delayed', label: 'DELAYED', tone: 'warn' };
  return { key: 'stale', label: 'STALE', tone: 'bad' };
}

export function machineCode(name) {
  const m = /^M-\d{3}/.exec(name || '');
  return m ? m[0] : String(name || '').slice(0, 12);
}
