import { useState } from 'react';
import StatusBadge from '../StatusBadge';
import { relTime } from '../../utils/relTime';

// Automatic live plan: every non-completed task grouped by order, plus the
// unplanned list with one-click attach into an approved plan.
export default function LivePlan({ data, loading, error, plans, onAttach, attaching }) {
  const [targetPlan, setTargetPlan] = useState('');
  const groups = data?.groups || [];
  const unplanned = data?.unplanned || [];
  const usablePlans = (plans || []).filter((p) => ['APPROVED', 'DISPATCHED'].includes(p.status));

  return (
    <section className="panel">
      <h2>Live plan</h2>
      <p className="muted">Automatic — every open task grouped by order, live from the database. No drafting needed.</p>
      {loading && <p className="muted">Loading live plan…</p>}
      {error && <div className="alert-banner" role="alert">{error}</div>}
      {!loading && !error && groups.length === 0 && <p className="muted">Nothing open. All tasks are done.</p>}
      {!loading && !error && groups.map((g, i) => (
        <div key={g.order ? g.order.id : `none-${i}`} style={{ marginTop: 12 }}>
          <h3 className="section-title" style={{ marginTop: 0 }}>
            {g.order ? `Order ${g.order.order_number}` : 'No order'}{' '}
            <StatusBadge tone="info">{g.tasks.length} open</StatusBadge>
          </h3>
          <ul className="task-list">
            {g.tasks.map((t) => (
              <li key={t.id} className="task-row">
                <div className="task-main">
                  <span className="cell-strong">{t.name}</span>
                  <span className="task-meta">
                    {t.status} · {Math.round((t.progress || 0) * 100)}%
                    {t.employee ? ` · ${t.employee.name}${t.employee.employee_code ? ` (${t.employee.employee_code})` : ''}` : ' · Unassigned'}
                    {t.machine ? ` · ${t.machine.name}` : ''}
                    {t.deadline ? ` · due ${new Date(t.deadline).toLocaleDateString()}` : ''}
                    {t.blocked ? ` · BLOCKED: ${t.blocked_reason}` : ''}
                    {t.overdue ? ' · OVERDUE' : ''}
                    {t.in_plan ? '' : ' · not in any plan'}
                  </span>
                </div>
                <span className="task-meta" title={t.updated_at || ''}>{relTime(t.updated_at)}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}

      <h3 className="section-title">Unplanned tasks ({unplanned.length})</h3>
      {unplanned.length === 0 && !loading && <p className="muted">Every open task is in a plan.</p>}
      {unplanned.length > 0 && (
        <>
          <div className="filter-bar" style={{ marginBottom: 8 }}>
            <select className="filter-select" value={targetPlan} onChange={(e) => setTargetPlan(e.target.value)} aria-label="Target plan">
              <option value="">Attach to plan…</option>
              {usablePlans.map((p) => <option key={p.id} value={p.id}>{p.title} ({p.status})</option>)}
            </select>
          </div>
          <ul className="task-list">
            {unplanned.map((t) => (
              <li key={t.id} className="task-row">
                <div className="task-main">
                  <span className="cell-strong">{t.name}</span>
                  <span className="task-meta">{t.status}{t.employee ? ` · ${t.employee.name}` : ' · Unassigned'}</span>
                </div>
                <button type="button" className="btn-small" disabled={!targetPlan || attaching === t.id}
                  onClick={() => onAttach(targetPlan, t.id)}>
                  {attaching === t.id ? '…' : 'Add to plan'}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
