import StatusBadge from '../StatusBadge';
import { formatDateTime, toneForProductionStatus } from './productionTone';

function progressPct(run) {
  const target = Number(run.quantity_target) || 0;
  const done = Number(run.quantity_completed) || 0;
  if (target <= 0) return null;
  return Math.min(100, Math.round((done / target) * 100));
}

export default function ProductionTable({
  runs,
  loading,
  orderById,
  taskById,
  machineById,
  onOpen,
  onEdit,
  onDelete,
  deletingId,
  onComplete,
  completingId,
}) {
  if (loading) return <p className="muted">Loading production runs…</p>;
  if (runs.length === 0) {
    return (
      <div className="empty-state">
        <p className="empty-title">No production runs registered yet.</p>
        <p className="muted">Start the first run to begin tracking execution output.</p>
      </div>
    );
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Run ID</th>
            <th>Order</th>
            <th>Task</th>
            <th>Machine</th>
            <th>Output</th>
            <th>Status</th>
            <th>Start</th>
            <th>Est. completion</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => {
            const order = orderById[r.order_id];
            const task = taskById ? taskById[r.task_id] : undefined;
            const machine = machineById[r.machine_id];
            const pct = progressPct(r);
            const finished = ['COMPLETED', 'DONE'].includes((r.status || '').toUpperCase());
            return (
              <tr key={r.id}>
                <td className="cell-mono">{String(r.id).slice(0, 8)}</td>
                <td className="cell-strong">{order ? order.order_number || String(order.id).slice(0, 8) : '—'}</td>
                <td className="cell-strong">{r.task_id ? (task ? task.name : String(r.task_id).slice(0, 8)) : '—'}</td>
                <td>{machine ? machine.name : '—'}</td>
                <td>
                  {r.quantity_completed ?? 0} / {r.quantity_target ?? 0}
                  {pct !== null && <span className="muted"> ({pct}%)</span>}
                </td>
                <td>
                  <StatusBadge tone={toneForProductionStatus(r.status)}>{r.status || '—'}</StatusBadge>
                </td>
                <td className="cell-mono">{formatDateTime(r.start_time)}</td>
                <td className="cell-mono">{formatDateTime(r.estimated_completion)}</td>
                <td className="cell-actions">
                  {!finished && onComplete && (
                    <button
                      type="button"
                      className="btn-small"
                      disabled={completingId === r.id}
                      onClick={() => onComplete(r)}
                      title="Mark this run COMPLETED (task/order update follows automatically)"
                    >
                      {completingId === r.id ? 'Saving…' : 'DONE'}
                    </button>
                  )}
                  <button type="button" className="btn-small" onClick={() => onOpen(r)}>
                    Details
                  </button>
                  <button type="button" className="btn-small" onClick={() => onEdit(r)}>
                    Edit
                  </button>
                  <button
                    type="button"
                    className="btn-small btn-danger"
                    disabled={deletingId === r.id}
                    onClick={() => onDelete(r)}
                  >
                    {deletingId === r.id ? 'Deleting…' : 'Delete'}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
