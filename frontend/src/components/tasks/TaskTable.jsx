import StatusBadge from '../StatusBadge';
import { formatDateTime, toneForTaskPriority, toneForTaskStatus } from './taskWorkflow';

function shortName(m, employees, machines, orders) {
  const bits = [];
  if (m.employee_id && employees[m.employee_id]) bits.push(employees[m.employee_id].name);
  if (m.machine_id && machines[m.machine_id]) {
    const code = /^M-\d{3}/.exec(machines[m.machine_id].name || '');
    bits.push(code ? code[0] : machines[m.machine_id].name);
  }
  if (m.order_id && orders[m.order_id]) bits.push(orders[m.order_id].order_number);
  return bits.join(' · ') || 'Unassigned';
}

export default function TaskTable({ tasks, loading, employees, machines, orders, onOpen, onAdvance, advancingId, onSuggest }) {
  if (loading) return <p className="muted">Loading tasks…</p>;
  if (tasks.length === 0) return <p className="muted">No tasks yet. Create them in Orders → Split.</p>;
  return (
    <table className="data-table">
      <thead>
        <tr><th>Task</th><th>Skill</th><th>Status</th><th>Priority</th><th>Assignment</th><th>Progress</th><th>Deadline</th><th>Actions</th></tr>
      </thead>
      <tbody>
        {tasks.map((t) => {
          const st = (t.status || 'PENDING').toUpperCase();
          const next = st === 'PENDING' ? 'IN_PROGRESS' : st === 'IN_PROGRESS' ? 'DONE' : null;
          const pct = Math.round((t.progress || 0) * 100);
          const late = t.deadline && ['PENDING', 'IN_PROGRESS'].includes(st) && new Date(t.deadline).getTime() < Date.now();
          return (
            <tr key={t.id}>
              <td className="cell-strong">{t.name}</td>
              <td className="muted">{t.required_skill || '—'}</td>
              <td><StatusBadge tone={toneForTaskStatus(t.status)}>{t.status || 'PENDING'}</StatusBadge></td>
              <td><StatusBadge tone={toneForTaskPriority(t.priority)}>{t.priority || 'NORMAL'}</StatusBadge></td>
              <td className="muted">{shortName(t, employees, machines, orders)}</td>
              <td style={{ minWidth: 110 }}>
                <div className="bar-track" title={`${pct}%`}>
                  <div className="bar-fill" style={{ width: `${pct}%` }} />
                </div>
                <span className="muted cell-mono">{pct}%</span>
              </td>
              <td className="cell-mono muted">{formatDateTime(t.deadline)}{late ? ' ⚠' : ''}</td>
              <td>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button type="button" className="btn-small" onClick={() => onOpen(t)}>Open</button>
                  {!t.employee_id && onSuggest && (
                    <button type="button" className="btn-small" onClick={() => onSuggest(t)} title="Rule-based assignment suggestion">
                      ✦ Suggest
                    </button>
                  )}
                  {next && (
                    <button
                      type="button"
                      className="btn-small"
                      disabled={advancingId === t.id}
                      onClick={() => onAdvance(t, next)}
                      title={`Move to ${next.replace('_', ' ')}`}
                    >
                      {advancingId === t.id ? '…' : next === 'DONE' ? '✓ Done' : '▶ Start'}
                    </button>
                  )}
                </div>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
