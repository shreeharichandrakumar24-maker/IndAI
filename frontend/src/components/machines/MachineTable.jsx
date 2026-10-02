import StatusBadge from '../StatusBadge';
import { toneForHealth, toneForMachineStatus } from './machineTone';

function fmtDate(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString();
}

export default function MachineTable({ machines, loading, onOpen, onEdit, onDelete, deletingId }) {
  if (loading) return <p className="muted">Loading machines…</p>;
  if (machines.length === 0) {
    return (
      <div className="empty-state">
        <p className="empty-title">No machines registered yet.</p>
        <p className="muted">Register the first machine to build the equipment fleet.</p>
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
            <th>Type</th>
            <th>Status</th>
            <th>Health</th>
            <th>Location</th>
            <th>Updated</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {machines.map((m) => (
            <tr key={m.id}>
              <td className="cell-strong">{m.name}</td>
              <td className="cell-mono">{String(m.id).slice(0, 8)}</td>
              <td>{m.machine_type || '—'}</td>
              <td>
                <StatusBadge tone={toneForMachineStatus(m.status)}>{m.status || '—'}</StatusBadge>
              </td>
              <td>
                <StatusBadge tone={toneForHealth(m.health_status)}>{m.health_status || '—'}</StatusBadge>
              </td>
              <td>{m.location || '—'}</td>
              <td className="cell-mono">{fmtDate(m.updated_at)}</td>
              <td className="cell-actions">
                <button type="button" className="btn-small" onClick={() => onOpen(m)}>
                  Details
                </button>
                <button type="button" className="btn-small" onClick={() => onEdit(m)}>
                  Edit
                </button>
                <button
                  type="button"
                  className="btn-small btn-danger"
                  disabled={deletingId === m.id}
                  onClick={() => onDelete(m)}
                >
                  {deletingId === m.id ? 'Deleting…' : 'Delete'}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
