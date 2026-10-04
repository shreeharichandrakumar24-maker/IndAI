import StatusBadge from '../StatusBadge';
import { relTime } from '../../utils/relTime';

function toneForLifecycle(s) {
  if (s === 'COMPLETED') return 'ok';
  if (s === 'IN_PROGRESS') return 'info';
  if (s === 'APPROVED' || s === 'DISPATCHED') return 'warn';
  return 'neutral';
}

function toneForTask(s) {
  if (s === 'DONE' || s === 'COMPLETED') return 'ok';
  if (s === 'IN_PROGRESS') return 'info';
  if (s === 'CANCELLED') return 'neutral';
  return 'warn';
}

// Per-plan live progress: header, filters, live item table, activity
// timeline. All task state is joined live by the backend on every read.
export default function ProgressTracker({ data, loading, error, plans, planId, onPlan,
  workerFilter, onWorkerFilter, statusFilter, onStatusFilter,
  overdueOnly, onOverdueOnly, onNavigate }) {
  const plan = data?.plan;
  const counts = plan?.counts || {};
  const allItems = data?.items || [];
  const items = allItems.filter((it) => {
    if (it.deleted) return true;
    const t = it.task || {};
    if (overdueOnly && !it.overdue) return false;
    if (statusFilter && (t.status || '') !== statusFilter) return false;
    if (workerFilter && !((t.employee?.name || '').toLowerCase().includes(workerFilter.toLowerCase()))) return false;
    return true;
  });
  const timeline = data?.timeline || [];

  return (
    <section className="panel">
      <h2>Progress tracker</h2>
      <div className="filter-bar" style={{ marginBottom: 12 }}>
        <select className="filter-select" value={planId || ''} onChange={(e) => onPlan(e.target.value)} aria-label="Plan">
          {(plans || []).filter((p) => p.status !== 'DRAFT').map((p) => (
            <option key={p.id} value={p.id}>{p.title} ({p.status})</option>
          ))}
        </select>
        <input className="filter-search" style={{ maxWidth: 220 }} value={workerFilter} onChange={(e) => onWorkerFilter(e.target.value)} placeholder="Filter by worker…" aria-label="Filter by worker" />
        <select className="filter-select" value={statusFilter} onChange={(e) => onStatusFilter(e.target.value)} aria-label="Task status">
          <option value="">All statuses</option>
          {['PENDING', 'IN_PROGRESS', 'COMPLETED', 'DONE', 'CANCELLED'].map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <label className="refresh-auto"><input type="checkbox" checked={overdueOnly} onChange={(e) => onOverdueOnly(e.target.checked)} /> Overdue only</label>
      </div>

      {loading && <p className="muted">Loading live progress…</p>}
      {error && <div className="alert-banner" role="alert">{error}</div>}
      {!loading && !error && !plan && <p className="muted">No approved plan yet. Approve a draft to start tracking.</p>}
      {!loading && !error && plan && (
        <>
          <div className="details-head">
            <h2 style={{ border: 'none', padding: 0, margin: 0 }}>{plan.title}{' '}
              <StatusBadge tone={toneForLifecycle(plan.status)}>{plan.status}</StatusBadge>{' '}
              {(plan.flags || []).map((f) => (
                <StatusBadge key={f} tone={f === 'BLOCKED' ? 'bad' : 'warn'}>{f}</StatusBadge>
              ))}
            </h2>
          </div>
          <div className="bar-row" style={{ marginBottom: 4 }}>
            <span className="bar-label">Progress</span>
            <div className="bar-track"><div className="bar-fill" style={{ width: `${Math.round((plan.progress || 0) * 100)}%` }} /></div>
            <span className="bar-count">{Math.round((plan.progress || 0) * 100)}%</span>
          </div>
          <p className="muted">
            {counts.done || 0} done · {counts.active || 0} active · {counts.pending || 0} pending
            {counts.blocked ? ` · ${counts.blocked} blocked` : ''}{counts.overdue ? ` · ${counts.overdue} overdue` : ''}
            {plan.approved_by?.name ? ` · approved by ${plan.approved_by.name}` : ''}
            {plan.approved_at ? ` · ${relTime(plan.approved_at)}` : ''}
          </p>

          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table className="data-table">
              <thead><tr><th>Task</th><th>Status</th><th>Worker</th><th>Machine</th><th>Deadline</th><th>Progress</th><th>Updated</th></tr></thead>
              <tbody>
                {items.map((it) => it.deleted ? (
                  <tr key={it.assignment_id}>
                    <td colSpan={7}>
                      <StatusBadge tone="warn">TASK DELETED</StatusBadge>{' '}
                      <span className="muted">This plan item&apos;s task was deleted. The plan record is kept; re-plan or ignore.</span>
                    </td>
                  </tr>
                ) : (
                  <tr key={it.assignment_id}>
                    <td className="cell-strong">{it.task.name}
                      {it.blocked && <div><StatusBadge tone="bad">BLOCKED</StatusBadge> <span className="muted">{it.task.blocked_reason}</span></div>}
                      {it.overdue && <div><StatusBadge tone="warn">OVERDUE</StatusBadge></div>}
                    </td>
                    <td><StatusBadge tone={toneForTask(it.task.status)}>{it.task.status}</StatusBadge></td>
                    <td>
                      {it.task.employee ? (
                        <span>{it.task.employee.name}{' '}
                          {it.task.employee.employee_code && (
                            <StatusBadge tone="neutral">{it.task.employee.employee_code}</StatusBadge>
                          )}
                        </span>
                      ) : <span className="muted">Unassigned</span>}
                    </td>
                    <td>{it.task.machine ? it.task.machine.name : <span className="muted">—</span>}</td>
                    <td className="cell-mono">{it.task.deadline ? new Date(it.task.deadline).toLocaleDateString() : '—'}</td>
                    <td style={{ minWidth: 110 }}>
                      <div className="bar-track"><div className="bar-fill" style={{ width: `${Math.round((it.task.progress || 0) * 100)}%` }} /></div>
                      {it.task.quantity_target ? <span className="muted"> {it.task.quantity_completed ?? 0}/{it.task.quantity_target}</span> : null}
                    </td>
                    <td className="muted" title={it.task.updated_at || ''}>{relTime(it.task.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {items.length === 0 && <p className="muted" style={{ marginTop: 8 }}>No items match the filters.</p>}
          <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
            <button type="button" className="btn-small" onClick={() => onNavigate && onNavigate('tasks')}>Open Tasks</button>
            <button type="button" className="btn-small" onClick={() => onNavigate && onNavigate('employees')}>Open Employees</button>
            <button type="button" className="btn-small" onClick={() => onNavigate && onNavigate('machines')}>Open Machines</button>
          </div>

          <h3 className="section-title">Activity timeline</h3>
          {timeline.length === 0 ? <p className="muted">No activity recorded yet. Worker updates and approvals appear here.</p> : (
            <ul className="task-list">
              {timeline.slice().reverse().slice(0, 30).map((e) => (
                <li key={e.id} className="task-row">
                  <div className="task-main">
                    <span className="cell-strong">{e.title}</span>
                    {e.description && <span className="task-meta">{e.description}</span>}
                  </div>
                  <span className="task-meta" title={e.at || ''}>{relTime(e.at)}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="muted" style={{ marginTop: 8 }}>
            Started/finished times come from worker reports
            {items.some((i) => i.started_estimated || i.finished_estimated)
              ? '; times marked “last update” are estimates (no report recorded yet).' : '.'}
          </p>
        </>
      )}
    </section>
  );
}
