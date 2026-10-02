import { useEffect, useState } from 'react';
import { api } from '../services/api';
import { formatDateTime } from './incidents/incidentWorkflow';

// Similar past events for one scope (F10): same machine first, then same
// order. Read-only; helps answer "have we seen this before?".
export default function SimilarMemory({ incidentId, machineId, orderId }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const params = {};
        if (incidentId) params.incident_id = incidentId;
        if (machineId) params.machine_id = machineId;
        if (orderId) params.order_id = orderId;
        const data = await api.similarMemory(params);
        if (!cancelled) setRows(Array.isArray(data) ? data : []);
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load similar events');
      }
    }
    if (incidentId || machineId || orderId) load();
    return () => { cancelled = true; };
  }, [incidentId, machineId, orderId]);

  if (!incidentId && !machineId && !orderId) return null;

  return (
    <div>
      <h3 className="section-title">Seen before? Similar past events</h3>
      {error ? (
        <p className="muted">{error}</p>
      ) : rows === null ? (
        <p className="muted">Loading past events…</p>
      ) : rows.length === 0 ? (
        <p className="muted">No similar past events on record.</p>
      ) : (
        <ul className="task-list">
          {rows.map((r) => (
            <li key={r.id} className="task-row">
              <div className="task-main">
                <span className="cell-strong">{r.title}</span>
                <span className="task-meta">
                  {formatDateTime(r.created_at)}
                  {r.description ? ` — ${r.description.slice(0, 140)}` : ''}
                  {r.resolution_action ? ` · Then: ${r.resolution_action.slice(0, 140)}` : ''}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
