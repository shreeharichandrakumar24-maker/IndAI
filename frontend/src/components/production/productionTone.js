// Badge tone + datetime helpers for production runs. Kept out of component
// files so Fast Refresh only sees components there.
export function toneForProductionStatus(status) {
  const s = (status || '').toUpperCase();
  if (s === 'COMPLETED' || s === 'DONE') return 'ok';
  if (s === 'IN_PROGRESS' || s === 'RUNNING') return 'info';
  if (s === 'CANCELLED' || s === 'FAILED' || s === 'BLOCKED') return 'bad';
  if (s === 'PLANNED' || s === 'PENDING' || s === 'PAUSED') return 'warn';
  return 'neutral';
}

export function formatDateTime(value) {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString();
}

// Convert an ISO timestamp to the "YYYY-MM-DDTHH:MM" shape used by
// <input type="datetime-local">. Empty string when absent/invalid.
export function toLocalInput(value) {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}
