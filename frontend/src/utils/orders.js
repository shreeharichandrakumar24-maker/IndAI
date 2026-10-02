// Shared order/task display helpers (kept out of component files so
// Fast Refresh only sees components there).
export function toneForOrderStatus(status) {
  const s = (status || '').toUpperCase();
  if (s === 'COMPLETED' || s === 'DONE') return 'ok';
  if (s === 'IN_PROGRESS' || s === 'IN REVIEW' || s === 'REVIEW') return 'info';
  if (s === 'DELAYED' || s === 'AT_RISK' || s === 'BLOCKED' || s === 'CANCELLED') return 'bad';
  if (s === 'PENDING' || s === 'PLANNED' || s === 'APPROVED') return 'warn';
  return 'neutral';
}

export function toneForTaskStatus(status) {
  const s = (status || '').toUpperCase();
  if (s === 'COMPLETED' || s === 'DONE') return 'ok';
  if (s === 'IN_PROGRESS') return 'info';
  if (s === 'BLOCKED' || s === 'CANCELLED') return 'bad';
  if (s === 'PENDING' || s === 'PLANNED') return 'warn';
  return 'neutral';
}

export function formatDateTime(value) {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString();
}
