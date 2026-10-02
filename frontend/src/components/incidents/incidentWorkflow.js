// Shared incident/maintenance workflow helpers (no components here, so
// Fast Refresh only sees components in component files).
//
// Incident statuses (convention): OPEN -> IN_PROGRESS -> RESOLVED
// Maintenance statuses (convention): PENDING -> IN_PROGRESS -> COMPLETED
//
// Incident<->Maintenance link (application convention, no DB FK):
//   maintenance.issue starts with "Incident <full-incident-uuid>: "

export const INCIDENT_STATUSES = ['OPEN', 'IN_PROGRESS', 'RESOLVED'];
export const MAINTENANCE_STATUSES = ['PENDING', 'IN_PROGRESS', 'COMPLETED'];

export function issuePrefix(incidentId) {
  return `Incident ${incidentId}: `;
}

export function linkedMaintenance(records, incidentId) {
  const prefix = issuePrefix(incidentId);
  return (records || []).filter((r) => (r.issue || '').startsWith(prefix));
}

export function stripIssuePrefix(issue, incidentId) {
  const prefix = issuePrefix(incidentId);
  return (issue || '').startsWith(prefix) ? issue.slice(prefix.length) : (issue || '');
}

export function isActiveIncident(incident) {
  return (incident?.status || 'OPEN').toUpperCase() !== 'RESOLVED';
}

export function toneForIncidentStatus(status) {
  const s = (status || '').toUpperCase();
  if (s === 'RESOLVED' || s === 'CLOSED') return 'ok';
  if (s === 'IN_PROGRESS') return 'info';
  if (s === 'OPEN') return 'bad';
  return 'neutral';
}

export function toneForSeverity(severity) {
  const s = (severity || '').toUpperCase();
  if (s === 'CRITICAL') return 'bad';
  if (s === 'HIGH') return 'warn';
  if (s === 'MEDIUM') return 'info';
  return 'neutral';
}

export function toneForMaintenanceStatus(status) {
  const s = (status || '').toUpperCase();
  if (s === 'COMPLETED' || s === 'DONE') return 'ok';
  if (s === 'IN_PROGRESS') return 'info';
  if (s === 'PENDING') return 'warn';
  return 'neutral';
}

export function formatDateTime(value) {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString();
}

// "YYYY-MM-DDTHH:MM" for <input type="datetime-local">.
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

export function machineCode(name) {
  const m = /^M-\d{3}/.exec(name || '');
  return m ? m[0] : String(name || '').slice(0, 12);
}
