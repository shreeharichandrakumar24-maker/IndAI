import StatusBadge from '../StatusBadge';

function toneForStatus(status) {
  const s = (status || '').toUpperCase();
  if (s === 'ACTIVE') return 'ok';
  if (s === 'ON_LEAVE' || s === 'ON LEAVE' || s === 'INACTIVE') return 'warn';
  return 'neutral';
}

function summarizeDict(value) {
  if (!value) return '—';
  if (Array.isArray(value)) {
    if (value.length === 0) return '—';
    return value.slice(0, 3).map(String).join(', ') + (value.length > 3 ? ` +${value.length - 3}` : '');
  }
  if (typeof value === 'object') {
    if (Array.isArray(value.items)) {
      if (value.items.length === 0) return '—';
      return value.items.slice(0, 3).map(String).join(', ') + (value.items.length > 3 ? ` +${value.items.length - 3}` : '');
    }
    const keys = Object.keys(value);
    if (keys.length === 0) return '—';
    return keys.slice(0, 3).join(', ') + (keys.length > 3 ? ` +${keys.length - 3}` : '');
  }
  return String(value);
}

export default function EmployeeTable({ employees, loading, onEdit, onDelete, deletingId, logins, onWorkerLogin }) {
  if (loading) return <p className="muted">Loading employees…</p>;
  if (employees.length === 0) {
    return (
      <div className="empty-state">
        <p className="empty-title">No employees registered yet.</p>
        <p className="muted">Add your first employee to build the workforce registry.</p>
      </div>
    );
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>ID</th>
            <th>Role</th>
            <th>Shift</th>
            <th>Status</th>
            <th>Availability</th>
            <th>Skills</th>
            <th>Login</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {employees.map((e) => (
            <tr key={e.id}>
              <td className="cell-strong">{e.name}{' '}
                {logins?.[e.id]?.employee_code && (
                  <StatusBadge tone="neutral">{logins[e.id].employee_code}</StatusBadge>
                )}
              </td>
              <td className="cell-mono">{String(e.id).slice(0, 8)}</td>
              <td>{e.role}</td>
              <td>{e.shift || '—'}</td>
              <td>
                <StatusBadge tone={toneForStatus(e.status)}>{e.status || '—'}</StatusBadge>
              </td>
              <td>{e.availability || '—'}</td>
              <td className="cell-truncate" title={JSON.stringify(e.skills || {})}>
                {summarizeDict(e.skills)}
              </td>
              <td>
                {logins?.[e.id]?.has_login ? (
                  <span title={`${logins[e.id].employee_code || ''} · ${logins[e.id].email || ''}`}>
                    <StatusBadge tone="ok">Has login</StatusBadge>
                  </span>
                ) : (
                  <StatusBadge tone="neutral">No login</StatusBadge>
                )}
              </td>
              <td className="cell-actions">
                <button type="button" className="btn-small" onClick={() => onWorkerLogin && onWorkerLogin(e)}>
                  Login
                </button>
                <button type="button" className="btn-small" onClick={() => onEdit(e)}>
                  Edit
                </button>
                <button
                  type="button"
                  className="btn-small btn-danger"
                  disabled={deletingId === e.id}
                  onClick={() => onDelete(e)}
                >
                  {deletingId === e.id ? 'Deleting…' : 'Delete'}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
