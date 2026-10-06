import { useCallback, useEffect, useState } from 'react';
import { api } from '../services/api';
import RefreshBar from '../components/RefreshBar';
import useAutoRefresh from '../hooks/useAutoRefresh';
import StatCard from '../components/StatCard';
import StatusBadge from '../components/StatusBadge';

function toCSVWeekly(report) {
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

function toCSVPeriod(report, label, start, end) {
  const lines = ['section,metric,value'];
  const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
  lines.push(`period,label,${label}`);
  lines.push(`period,start,${start}`);
  lines.push(`period,end,${end}`);
  const push = (section, obj) => {
    for (const [k, v] of Object.entries(obj || {})) {
      if (v !== null && typeof v === 'object') continue;
      lines.push([section, k, v].map(esc).join(','));
    }
  };
  push('orders', report.orders);
  push('production', report.production);
  push('tasks', report.tasks);
  push('downtime', report.downtime);
  push('maintenance', report.maintenance);
  push('telemetry', report.telemetry);
  for (const m of report.top_failing_machines || []) {
    lines.push(['top_machine', `${m.code} ${m.name}`, m.incidents].map(esc).join(','));
  }
  for (const o of report.orders.late_orders || []) {
    lines.push(['late_order', o.order_number, `${o.status} due ${o.deadline}`].map(esc).join(','));
  }
  return lines.join('\n');
}

function toCSVOrder(r) {
  const lines = ['section,metric,value'];
  const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
  const o = r.order || {};
  lines.push(['order', 'order_number', o.order_number].map(esc).join(','));
  lines.push(['order', 'customer', o.customer_name].map(esc).join(','));
  lines.push(['order', 'product', o.product].map(esc).join(','));
  lines.push(['order', 'status', o.status].map(esc).join(','));
  lines.push(['order', 'report_label', o.report_label].map(esc).join(','));
  const push = (section, obj) => {
    for (const [k, v] of Object.entries(obj || {})) {
      if (v !== null && typeof v === 'object') continue;
      lines.push([section, k, v].map(esc).join(','));
    }
  };
  push('summary', r.summary);
  for (const t of r.tasks?.items || []) {
    lines.push(['task', t.name, `${t.status} ${Math.round((t.progress || 0) * 100)}%`].map(esc).join(','));
  }
  for (const i of [...(r.incidents?.linked || []), ...(r.incidents?.related || [])]) {
    lines.push(['incident', i.incident_type, `${i.severity} ${i.status}`].map(esc).join(','));
  }
  return lines.join('\n');
}

function downloadText(filename, text) {
  const blob = new Blob([text], { type: 'text/csv' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

function currentMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

// Weekly operations summary for reviews and meetings. Deterministic
// backend aggregates; CSV downloads from the same JSON; print via browser.
export default function Reports() {
  const [tab, setTab] = useState('weekly');
  const [offset, setOffset] = useState(0);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [month, setMonth] = useState(currentMonth());
  const [mreport, setMreport] = useState(null);
  const [mloading, setMloading] = useState(false);
  const [merror, setMerror] = useState('');

  const [orders, setOrders] = useState([]);
  const [orderId, setOrderId] = useState('');
  const [oreport, setOreport] = useState(null);
  const [oloading, setOloading] = useState(false);
  const [oerror, setOerror] = useState('');

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

  const loadMonthly = useCallback(async () => {
    if (!month) { setMerror('Pick a month first.'); return; }
    setMloading(true); setMerror('');
    try {
      setMreport(await api.monthlyReport(month));
    } catch (err) {
      setMerror(err.message || 'Failed to load monthly report');
    } finally {
      setMloading(false);
    }
  }, [month]);

  const loadOrders = useCallback(async () => {
    try {
      const list = await api.orders();
      setOrders(Array.isArray(list) ? list : []);
    } catch { setOrders([]); }
  }, []);

  const loadOrderReport = useCallback(async (id) => {
    if (!id) return;
    setOloading(true); setOerror('');
    try {
      setOreport(await api.orderReport(id));
    } catch (err) {
      setOerror(err.message || 'Failed to load order report');
      setOreport(null);
    } finally {
      setOloading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (tab === 'monthly' && !mreport && !mloading) loadMonthly(); }, [tab, mreport, mloading, loadMonthly]);
  useEffect(() => { if (tab === 'order') loadOrders(); }, [tab, loadOrders]);

  const refreshActive = useCallback(async (quiet = false) => {
    if (tab === 'monthly') { if (!quiet) loadMonthly(); }
    else if (tab === 'order') { if (orderId) loadOrderReport(orderId); }
    else await load(quiet);
  }, [tab, load, loadMonthly, orderId, loadOrderReport]);
  const refresher = useAutoRefresh(refreshActive);

  const downloadCSV = () => {
    if (!report) return;
    downloadText(`indai-weekly-${(report.week_start || '').slice(0, 10)}.csv`, toCSVWeekly(report));
  };
  const downloadMonthlyCSV = () => {
    if (!mreport) return;
    downloadText(`indai-monthly-${mreport.month}.csv`,
      toCSVPeriod(mreport, mreport.month, mreport.period_start, mreport.period_end));
  };
  const downloadOrderCSV = () => {
    if (!oreport) return;
    downloadText(`indai-order-${oreport.order.order_number || oreport.order.id}.csv`, toCSVOrder(oreport));
  };

  const weekLabel = report
    ? `${new Date(report.week_start).toLocaleDateString()} – ${new Date(report.week_end).toLocaleDateString()}`
    : '';
  const monthLabel = mreport
    ? `${new Date(mreport.period_start).toLocaleDateString()} – ${new Date(mreport.period_end).toLocaleDateString()}`
    : '';

  const tabs = [['weekly', 'Weekly'], ['monthly', 'Monthly'], ['order', 'Order Final']];

  return (
    <div className="page">
      <RefreshBar auto={refresher.auto} onAuto={refresher.setAuto} onReload={refresher.refreshNow} refreshing={refresher.refreshing} lastRefresh={refresher.lastRefresh} />
      <div className="page-head">
        <div>
          <h2>Reports</h2>
          <p className="page-desc">
            {tab === 'order'
              ? 'Final report for a completed order — or a current snapshot while it is still in progress.'
              : tab === 'monthly'
                ? `Orders, output, machines and decisions — ${monthLabel}. Matches on-screen numbers exactly.`
                : `Orders, breakdowns, failing machines and decisions — ${weekLabel}. Matches on-screen numbers exactly.`}
          </p>
        </div>
        <div className="no-print" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {tabs.map(([id, label]) => (
            <button key={id} type="button" className={tab === id ? 'btn-primary' : 'btn-secondary'}
              onClick={() => setTab(id)}>{label}</button>
          ))}
        </div>
      </div>

      {tab === 'weekly' && (
        <>
          <div className="no-print" style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <select value={offset} onChange={(e) => setOffset(Number(e.target.value))} aria-label="Week">
              {[0, 1, 2, 3].map((n) => (
                <option key={n} value={n}>{n === 0 ? 'This week' : `${n} week${n > 1 ? 's' : ''} ago`}</option>
              ))}
            </select>
            <button type="button" className="btn-secondary" onClick={downloadCSV} disabled={!report}>⬇ CSV</button>
            <button type="button" className="btn-primary" onClick={() => window.print()} disabled={!report}>🖨 Print</button>
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
        </>
      )}

      {tab === 'monthly' && (
        <>
          <div className="no-print" style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <input type="month" value={month} onChange={(e) => { setMonth(e.target.value); setMreport(null); }} aria-label="Month" />
            <button type="button" className="btn-primary" onClick={loadMonthly} disabled={mloading || !month}>
              {mloading ? 'Loading…' : 'Load month'}
            </button>
            <button type="button" className="btn-secondary" onClick={downloadMonthlyCSV} disabled={!mreport}>⬇ CSV</button>
            <button type="button" className="btn-primary" onClick={() => window.print()} disabled={!mreport}>🖨 Print</button>
          </div>

          {merror && <div className="alert-banner no-print" role="alert">{merror}</div>}
          {mloading && <p className="muted">Loading monthly report…</p>}
          {!mloading && !mreport && !merror && <p className="muted">Pick a month and load the report.</p>}

          {mreport && (
            <>
              <section className="stat-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
                <StatCard label="Completed in period" value={mreport.orders.completed_this_week} sub={`${mreport.orders.active_total} active`} loading={false} />
                <StatCard label="Output" value={`${mreport.production.completed_quantity} / ${mreport.production.target_quantity}`} sub={`${mreport.production.run_count} runs`} loading={false} />
                <StatCard label="Breakdowns" value={mreport.downtime.incidents_raised_this_week} sub={`${mreport.downtime.currently_open} still open`} loading={false} />
                <StatCard label="Tasks done" value={mreport.tasks.completed} sub={`${mreport.tasks.open} open of ${mreport.tasks.total}`} loading={false} />
              </section>

              <section className="panel">
                <h2>Top failing machines</h2>
                {mreport.top_failing_machines.length === 0 ? <p className="muted">No incidents this month.</p> : (
                  <table className="data-table">
                    <thead><tr><th>Code</th><th>Machine</th><th>Incidents</th></tr></thead>
                    <tbody>
                      {mreport.top_failing_machines.map((m) => (
                        <tr key={m.machine_id}><td className="cell-mono">{m.code}</td><td className="cell-strong">{m.name}</td><td>{m.incidents}</td></tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </section>

              <section className="panel">
                <h2>Late orders</h2>
                {mreport.orders.late_orders.length === 0 ? <p className="muted">Nothing late. 🎉</p> : (
                  <ul className="task-list">
                    {mreport.orders.late_orders.map((o) => (
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

              <section className="panel">
                <h2>More in this period</h2>
                <p className="muted">
                  Maintenance events <b>{mreport.maintenance.events_this_period}</b>
                  {' · '}telemetry samples <b>{mreport.telemetry.samples_this_period}</b>
                  {' '}({mreport.telemetry.abnormal_readings} abnormal)
                  {' · '}open tasks assigned <b>{mreport.employees.assigned_open_tasks}</b>
                  {' · '}decisions <b>{mreport.decisions.admin_decisions_this_week}</b>
                  {' '}({mreport.decisions.recommendations_approved} approved / {mreport.decisions.recommendations_rejected} rejected)
                </p>
              </section>
            </>
          )}
        </>
      )}

      {tab === 'order' && (
        <>
          <div className="no-print" style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
            <select value={orderId} onChange={(e) => { setOrderId(e.target.value); setOreport(null); setOerror(''); if (e.target.value) loadOrderReport(e.target.value); }} aria-label="Order">
              <option value="">— choose an order —</option>
              {orders.map((o) => (
                <option key={o.id} value={o.id}>{o.order_number} ({o.status})</option>
              ))}
            </select>
            <button type="button" className="btn-secondary" onClick={downloadOrderCSV} disabled={!oreport}>⬇ CSV</button>
            <button type="button" className="btn-primary" onClick={() => window.print()} disabled={!oreport}>🖨 Print</button>
          </div>

          {oerror && <div className="alert-banner no-print" role="alert">{oerror}</div>}
          {oloading && <p className="muted">Loading order report…</p>}
          {!oloading && !oreport && !oerror && <p className="muted">Choose an order to see its report. Completing an order makes its Final Report available here immediately.</p>}

          {oreport && (
            <>
              <div style={{ marginBottom: 12 }}>
                <StatusBadge tone={oreport.order.is_final ? 'ok' : 'info'}>
                  {oreport.order.is_final ? 'Final Report' : 'Order Report'}
                </StatusBadge>
              </div>

              <section className="panel">
                <h2>1 · Order summary</h2>
                <table className="data-table"><tbody>
                  {[
                    ['Order', oreport.order.order_number],
                    ['Customer', oreport.order.customer_name || '—'],
                    ['Product', oreport.order.product || '—'],
                    ['Quantity', oreport.order.quantity ?? '—'],
                    ['Priority', oreport.order.priority || '—'],
                    ['Status', oreport.order.status || '—'],
                    ['Deadline', oreport.order.deadline ? new Date(oreport.order.deadline).toLocaleString() : '—'],
                    ['Last updated', oreport.order.updated_at ? new Date(oreport.order.updated_at).toLocaleString() : '—'],
                  ].map(([k, v]) => (
                    <tr key={k}><td className="cell-strong">{k}</td><td>{String(v)}</td></tr>
                  ))}
                </tbody></table>
              </section>

              <section className="panel">
                <h2>2 · Production summary</h2>
                <p className="muted">
                  {oreport.production.run_count} runs · target <b>{oreport.production.target_quantity}</b> ·
                  completed <b>{oreport.production.completed_quantity}</b> ·
                  remaining <b>{oreport.production.run_count ? Math.max(0, oreport.production.target_quantity - oreport.production.completed_quantity) : Math.max(0, (oreport.order.quantity || 0) - oreport.production.completed_quantity)}</b>
                </p>
                {oreport.production.runs.length === 0 ? <p className="muted">No production runs linked.</p> : (
                  <table className="data-table">
                    <thead><tr><th>Status</th><th>Target</th><th>Done</th><th>Machine</th></tr></thead>
                    <tbody>
                      {oreport.production.runs.map((r) => (
                        <tr key={r.id}>
                          <td><StatusBadge tone={['COMPLETED', 'DONE'].includes((r.status || '').toUpperCase()) ? 'ok' : 'info'}>{r.status}</StatusBadge></td>
                          <td className="cell-mono">{r.quantity_target}</td>
                          <td className="cell-mono">{r.quantity_completed}</td>
                          <td className="cell-mono">{(r.machine_id || '').slice(0, 8) || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </section>

              <section className="panel">
                <h2>3 · Tasks ({oreport.tasks.completed}/{oreport.tasks.total} done)</h2>
                {oreport.tasks.items.length === 0 ? <p className="muted">No tasks linked.</p> : (
                  <table className="data-table">
                    <thead><tr><th>Task</th><th>Status</th><th>Progress</th><th>Assignee</th></tr></thead>
                    <tbody>
                      {oreport.tasks.items.map((t) => (
                        <tr key={t.id}>
                          <td className="cell-strong">{t.name}</td>
                          <td>{t.status}</td>
                          <td className="cell-mono">{Math.round((t.progress || 0) * 100)}%</td>
                          <td>{t.employee_name || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </section>

              <section className="panel">
                <h2>4 · Machines used ({oreport.machines.count})</h2>
                {oreport.machines.used.length === 0 ? <p className="muted">No machines linked.</p> : (
                  <table className="data-table">
                    <thead><tr><th>Machine</th><th>Type</th><th>Status</th></tr></thead>
                    <tbody>
                      {oreport.machines.used.map((m) => (
                        <tr key={m.id}>
                          <td className="cell-strong">{m.name}{m.machine_code ? ` (${m.machine_code})` : ''}</td>
                          <td>{m.machine_type || '—'}</td>
                          <td>{m.status || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </section>

              <section className="panel">
                <h2>5 · Incidents ({oreport.incidents.linked_count} linked, {oreport.incidents.related_count} related)</h2>
                {(oreport.incidents.linked.length + oreport.incidents.related.length) === 0 ? <p className="muted">None.</p> : (
                  <ul className="task-list">
                    {[...oreport.incidents.linked.map((i) => ({ ...i, rel: 'linked' })),
                      ...oreport.incidents.related.map((i) => ({ ...i, rel: `via ${(i.via || []).join('+')}` }))].map((i) => (
                      <li key={i.id} className="task-row">
                        <div className="task-main">
                          <span className="cell-strong">{i.severity}</span>
                          <span className="task-meta">{i.incident_type} · {i.rel} · {i.created_at ? new Date(i.created_at).toLocaleString() : '—'}</span>
                        </div>
                        <div className="task-badges"><StatusBadge tone={i.status === 'OPEN' ? 'bad' : 'info'}>{i.status}</StatusBadge></div>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section className="panel">
                <h2>6 · Maintenance ({oreport.maintenance.count})</h2>
                <p className="muted">{oreport.maintenance.note}</p>
                {oreport.maintenance.events.length === 0 ? <p className="muted">None.</p> : (
                  <ul className="task-list">
                    {oreport.maintenance.events.map((m) => (
                      <li key={m.id} className="task-row">
                        <div className="task-main">
                          <span className="cell-strong">{m.machine_name || '—'}</span>
                          <span className="task-meta">{m.issue} · {m.status}</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section className="panel">
                <h2>7 · AI insights</h2>
                {(oreport.ai.recommendation_count + oreport.ai.memory_count) === 0
                  ? <p className="muted">No AI recommendations or notes explicitly linked to this order.</p>
                  : (
                    <ul className="task-list">
                      {oreport.ai.recommendations.map((r) => (
                        <li key={r.id} className="task-row">
                          <div className="task-main">
                            <span className="cell-strong">{r.recommendation_type}</span>
                            <span className="task-meta">{(r.recommendation || '').slice(0, 140)}</span>
                          </div>
                          <div className="task-badges"><StatusBadge tone="info">{r.status}</StatusBadge></div>
                        </li>
                      ))}
                      {oreport.ai.memory.map((m) => (
                        <li key={m.id} className="task-row">
                          <div className="task-main">
                            <span className="cell-strong">{m.event_type}</span>
                            <span className="task-meta">{(m.title || '').slice(0, 140)}</span>
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
              </section>
            </>
          )}
        </>
      )}
    </div>
  );
}
