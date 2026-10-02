import StatusBadge from '../StatusBadge';
import { formatDateTime, toneForProductionStatus } from './productionTone';

// Details modal for one run: the actual ProductionRunResponse record plus the
// linked order / task / machine resolved from the page-level lookup lists.
// No extra API calls — missing links render as "record not found".
export default function ProductionDetails({ run, orderById, taskById, machineById, onClose }) {
  if (!run) return null;
  const order = orderById[run.order_id];
  const task = taskById[run.task_id];
  const machine = machineById[run.machine_id];

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal modal-wide"
        role="dialog"
        aria-modal="true"
        aria-label={`Production run ${String(run.id).slice(0, 8)} details`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="details-head">
          <h2>
            Run <span className="cell-mono">{String(run.id).slice(0, 8)}</span>
          </h2>
          <button type="button" className="btn-small" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="details-grid">
          <div>
            <span className="detail-label">Status</span>
            <span className="detail-value">
              <StatusBadge tone={toneForProductionStatus(run.status)}>{run.status || '—'}</StatusBadge>
            </span>
          </div>
          <div>
            <span className="detail-label">Quantity target</span>
            <span className="detail-value">{run.quantity_target ?? '—'}</span>
          </div>
          <div>
            <span className="detail-label">Quantity completed</span>
            <span className="detail-value">{run.quantity_completed ?? '—'}</span>
          </div>
          <div>
            <span className="detail-label">Start time</span>
            <span className="detail-value cell-mono">{formatDateTime(run.start_time)}</span>
          </div>
          <div>
            <span className="detail-label">Estimated completion</span>
            <span className="detail-value cell-mono">{formatDateTime(run.estimated_completion)}</span>
          </div>
          <div>
            <span className="detail-label">Created</span>
            <span className="detail-value cell-mono">{formatDateTime(run.created_at)}</span>
          </div>
          <div>
            <span className="detail-label">Updated</span>
            <span className="detail-value cell-mono">{formatDateTime(run.updated_at)}</span>
          </div>
          <div>
            <span className="detail-label">Full run ID</span>
            <span className="detail-value cell-mono" title={run.id}>
              {String(run.id).slice(0, 8)}
            </span>
          </div>
        </div>

        <h3 className="section-title">Order → Run → Task → Machine</h3>
        <div className="details-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
          <div>
            <span className="detail-label">Order</span>
            <span className="detail-value">
              {!run.order_id
                ? 'Unlinked'
                : order
                  ? `${order.order_number || String(order.id).slice(0, 8)}${order.customer_name ? ` · ${order.customer_name}` : ''}${order.product ? ` · ${order.product}` : ''}`
                  : 'Order record not found'}
            </span>
          </div>
          <div>
            <span className="detail-label">Task</span>
            <span className="detail-value">
              {!run.task_id ? 'Unlinked' : task ? task.name : 'Task record not found'}
            </span>
          </div>
          <div>
            <span className="detail-label">Machine</span>
            <span className="detail-value">
              {!run.machine_id ? 'Unlinked' : machine ? machine.name : 'Machine record not found'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
