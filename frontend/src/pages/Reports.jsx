import { useCallback, useEffect, useState } from 'react';
import { api } from '../services/api';
import RefreshBar from '../components/RefreshBar';
import useAutoRefresh from '../hooks/useAutoRefresh';
import StatCard from '../components/StatCard';
import StatusBadge from '../components/StatusBadge';

function toCSV(report) {
  const lines = ['section,metric,value'];
  const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
  lines.push(`week,start,${report.week_start}`);
  lines.push(`week,end,${report.week_end}`);
  lines.push(['orders', 'completed_this_week', report.orders.completed_this_week].map(esc).join(','));
  lines.push(['orders', 'late_now', report.orders.late_now].map(esc).join(','));
  lines.push(['orders', 'active_total', report.orders.active_total].map(esc).join(','));
  lines.push(['downtime', 'incidents_raised_this_week', report.downtime.incidents_raised_this_week].map(esc).join(','));
  lines.push(['downtime', 'currently_open', report.downtime.currently_open].map(esc).join(','));
  lines.push(['decisions', 'admin_decisions_this_week', report.decisions.admin_decisions_this_week].map(esc).join(','));
  lines.push(['decisions', 'recommendations_approved', report.decisions.recommendations_approved].map(esc).join(','));
  lines.push(['decisions', 'recommendations_rejected', report.decisions.recommendations_rejected].map(esc).join(','));
  for (const m of report.top_failing_machines || []) {
    lines.push(['top_machine', `${m.code} ${m.name}`, m.incidents].map(esc).join(','));
  }
  for (const o of report.orders.late_orders || []) {
    lines.push(['late_order', o.order_number, `${o.status} due ${o.deadline}`].map(esc).join(','));
  }
  return lines.join('\n');
}

// Weekly operations summary for reviews and meetings. Deterministic
// backend aggregates; CSV downloads from the same JSON; print via browser.
export default function Reports() {
  const [offset, setOffset] = useState(0);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    setError('');
    try {
      const data = await api.weeklyReport(offset);
      setReport(data);
    } catch (err) {
      setError(err.message || 'Failed to load report');
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [offset]);

  useEffect(() => { load(); }, [load]);

  const downloadCSV = () => {
    if (!report) return;
    const blob = new Blob([toCSV(report)], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `indai-weekly-${(report.week_start || '').slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const weekLabel = report
    ? `${new Date(report.week_start).toLocaleDateString()} – ${new Date(report.week_end).toLocaleDateString()}`
    : '';

  const refresher = useAutoRefresh(load);

  return (
    <div className="page">
      <RefreshBar auto={refresher.auto} onAuto={refresher.setAuto} onReload={refresher.refreshNow} refreshing={refresher.refreshing} lastRefresh={refresher.lastRefresh} />
      <div className="page-head">
        <div>
          <h2>Weekly report</h2>
          <p className="page-desc">Orders, breakdowns, failing machines and decisions — {weekLabel}. Matches on-screen numbers exactly.</p>
        </div>
        <div className="no-print" style={{ display: 'flex', gap: 8 }}>
          <select value={offset} onChange={(e) => setOffset(Number(e.target.value))} aria-label="Week">
            {[0, 1, 2, 3].map((n) => (
              <option key={n} value={n}>{n === 0 ? 'This week' : `${n} week${n > 1 ? 's' : ''} ago`}</option>
            ))}
          </select>
          <button type="button" className="btn-secondary" onClick={downloadCSV} disabled={!report}>⬇ CSV</button>
          <button type="button" className="btn-primary" onClick={() => window.print()} disabled={!report}>🖨 Print</button>
        </div>
      </div>

      {error && <div className="alert-banner no-print" role="alert">{error} <button type="button" className="btn-small" onClick={load}>Retry</button></div>}

      {loading ? <p className="muted">Loading report…</p> : report && (
        <>
          <section className="stat-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
            <StatCard label="Completed this week" value={report.orders.completed_this_week} sub={`${report.orders.active_total} active`} loading={false} />
            <StatCard label="Late orders" value={report.orders.late_now} sub="deadline passed" loading={false} />
            <StatCard label="Breakdowns" value={report.downtime.incidents_raised_this_week} sub={`${report.downtime.currently_open} still open`} loading={false} />
            <StatCard label="Decisions" value={report.decisions.admin_decisions_this_week} sub={`${report.decisions.recommendations_approved} approved / ${report.decisions.recommendations_rejected} rejected`} loading={false} />
          </section>

          <section className="panel">
            <h2>Top failing machines</h2>
            {report.top_failing_machines.length === 0 ? <p className="muted">No incidents this week.</p> : (
              <table className="data-table">
                <thead><tr><th>Code</th><th>Machine</th><th>Incidents</th></tr></thead>
                <tbody>
                  {report.top_failing_machines.map((m) => (
                    <tr key={m.machine_id}><td className="cell-mono">{m.code}</td><td className="cell-strong">{m.name}</td><td>{m.incidents}</td></tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section className="panel">
            <h2>Late orders</h2>
            {report.orders.late_orders.length === 0 ? <p className="muted">Nothing late. 🎉</p> : (
              <ul className="task-list">
                {report.orders.late_orders.map((o) => (
                  <li key={o.order_number} className="task-row">
                    <div className="task-main">
                      <span className="cell-strong">{o.order_number}</span>
                      <span className="task-meta">due {o.deadline ? new Date(o.deadline).toLocaleString() : '—'}</span>
                    </div>
                    <div className="task-badges"><StatusBadge tone="bad">{o.status}</StatusBadge></div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
