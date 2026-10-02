import StatusBadge from '../StatusBadge';

function fmtReading(value, digits = 1) {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  return Number.isNaN(n) ? '—' : n.toFixed(digits);
}

function ageText(timestamp) {
  if (!timestamp) return 'no readings yet';
  const ms = Date.now() - new Date(timestamp).getTime();
  if (Number.isNaN(ms)) return String(timestamp);
  if (ms < 0) return 'just now';
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s ago`;
  return `${Math.floor(s / 60)}m ago`;
}

// Side panel for the selected map node: latest readings, linked run/task/
// order/employee in readable labels, open incidents, navigation buttons.
export default function MachineSidePanel({ data, onNavigate, onClose }) {
  if (!data) {
    return (
      <div className="panel">
        <h2>Machine</h2>
        <p className="muted">Select a machine on the map.</p>
      </div>
    );
  }
  const { machine, latest, run, task, order, employee, incidents } = data;
  const open = (incidents || []).filter((i) => (i.status || 'OPEN').toUpperCase() !== 'RESOLVED');
  const firstOpen = open[0] || null;

  return (
    <div className="panel">
      <div className="details-head">
        <h2>{data.code} <span className="muted">— {machine.name}</span></h2>
        <button type="button" className="btn-small" onClick={onClose}>Close</button>
      </div>

      <div className="details-grid">
        <div>
          <span className="detail-label">State (rule-based)</span>
          <span className="detail-value">
            <StatusBadge tone={data.tone === 'ok' ? 'ok' : data.tone === 'stale' ? 'neutral' : 'bad'}>
              {data.stateLabel}
            </StatusBadge>
          </span>
        </div>
        <div>
          <span className="detail-label">Latest reading</span>
          <span className="detail-value cell-mono">{ageText(latest?.timestamp)}</span>
        </div>
      </div>

      <h3 className="section-title">Readings</h3>
      <p className="muted cell-mono">
        {fmtReading(latest?.temperature)} °C · {fmtReading(latest?.vibration, 2)} vib ·{' '}
        {fmtReading(latest?.current, 2)} A · {fmtReading(latest?.rpm, 0)} rpm · {latest?.machine_status || '—'}
      </p>

      <h3 className="section-title">Linked work</h3>
      <p className="muted">Run: {run ? `${run.status} (${run.quantity_completed ?? 0}/${run.quantity_target ?? 0})` : '—'}</p>
      <p className="muted">Task: {task ? `${task.name} (${task.status})` : '—'}</p>
      <p className="muted">Order: {order ? `${order.order_number} (${order.status})` : '—'}</p>
      <p className="muted">Employee: {employee ? `${employee.name} (${employee.role})` : '—'}</p>

      <h3 className="section-title">Open incidents ({open.length})</h3>
      {open.length === 0 ? (
        <p className="muted">None.</p>
      ) : (
        <ul className="task-list">
          {open.map((i) => (
            <li key={i.id} className="task-row">
              <div className="task-main">
                <span className="cell-strong">{i.severity}</span>
                <span className="task-meta">{(i.description || '').slice(0, 120)}</span>
              </div>
              <div className="task-badges">
                <StatusBadge tone="bad">{i.status || 'OPEN'}</StatusBadge>
              </div>
            </li>
          ))}
        </ul>
      )}

      <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button type="button" className="btn-secondary" onClick={() => onNavigate('machines', { machineId: machine.id })}>
          Machine details
        </button>
        <button type="button" className="btn-secondary" onClick={() => onNavigate('iot', { machineId: machine.id })}>
          IoT monitoring
        </button>
        {firstOpen && (
          <>
            <button type="button" className="btn-primary" onClick={() => onNavigate('incidents', { incidentId: firstOpen.id })}>
              Open incident
            </button>
            <button type="button" className="btn-secondary" onClick={() => onNavigate('incidents', { incidentId: firstOpen.id })}>
              Analyze with AI
            </button>
          </>
        )}
        {order && (
          <button type="button" className="btn-secondary" onClick={() => onNavigate('orders', { orderId: order.id })}>
            Open order
          </button>
        )}
      </div>
    </div>
  );
}
