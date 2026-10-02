export const TASK_STATUSES = ['PENDING', 'IN_PROGRESS', 'DONE'];
export const TASK_PRIORITIES = ['LOW', 'NORMAL', 'HIGH', 'URGENT'];

export function toneForTaskStatus(status) {
  const s = (status || '').toUpperCase();
  if (s === 'DONE' || s === 'COMPLETED') return 'ok';
  if (s === 'IN_PROGRESS') return 'info';
  if (s === 'PENDING') return 'warn';
  if (s === 'CANCELLED') return 'neutral';
  return 'neutral';
}

export function toneForTaskPriority(priority) {
  const p = (priority || '').toUpperCase();
  if (p === 'URGENT') return 'bad';
  if (p === 'HIGH') return 'warn';
  if (p === 'NORMAL') return 'info';
  return 'neutral';
}

export function isOpenTask(t) {
  return !['DONE', 'COMPLETED', 'CANCELLED'].includes((t?.status || '').toUpperCase());
}

export function formatDateTime(value) {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString();
}
