import { useCallback, useEffect, useState } from 'react';
import { api } from '../services/api';
import StatCard from '../components/StatCard';
import StatusBadge from '../components/StatusBadge';
import BossView from './BossView';
import RefreshBar from '../components/RefreshBar';
import useAutoRefresh from '../hooks/useAutoRefresh';

function valueOf(result) {
  return result.status === 'fulfilled' ? result.value : null;
}

function toneForMachine(machine) {
  const h = (machine.health_status || '').toUpperCase();
  if (h === 'GOOD') return 'ok';
  if (h === 'WARNING' || h === 'DEGRADED') return 'warn';
  if (h === 'CRITICAL' || h === 'POOR' || h === 'DOWN') return 'bad';
  return 'neutral';
}

function toneForIncident(incident) {
  const s = (incident.severity || '').toUpperCase();
  if (s === 'CRITICAL' || s === 'HIGH') return 'bad';
  if (s === 'MEDIUM') return 'warn';
  return 'info';
}

function toneForOrderStatus(status) {
  const s = (status || '').toUpperCase();
  if (s === 'COMPLETED' || s === 'DONE') return 'ok';
  if (s === 'IN_PROGRESS' || s === 'IN PROGRESS') return 'info';
  if (s === 'DELAYED' || s === 'AT_RISK' || s === 'BLOCKED') return 'bad';
  if (s === 'PENDING' || s === 'PLANNED') return 'warn';
  return 'neutral';
}

export default function Dashboard() {
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState([]);
  const [bossView, setBossView] = useState(true); // plain-language first
  const [data, setData] = useState({
    employees: [],
    machines: [],
    orders: [],
    tasks: [],
    production: [],
    incidents: [],
  });

  const load = useCallback(async (quiet = false) => {
    // allSettled: one slow/failing endpoint must not crash the dashboard.
    if (!quiet) setLoading(true);
    const [employees, machines, orders, tasks, production, incidents] =
      await Promise.allSettled([
        api.employees(),
        api.machines(),
        api.orders(),
        api.tasks(),
        api.production(),
        api.incidents(),
      ]);
    const names = ['employees', 'machines', 'orders', 'tasks', 'production', 'incidents'];
    const results = [employees, machines, orders, tasks, production, incidents];
    setFailed(names.filter((_, i) => results[i].status === 'rejected'));
    setData({
      employees: valueOf(employees) || [],
      machines: valueOf(machines) || [],
      orders: valueOf(orders) || [],
      tasks: valueOf(tasks) || [],
      production: valueOf(production) || [],
      incidents: valueOf(incidents) || [],
    });
    if (!quiet) setLoading(false);
  }, []);

  const refresher = useAutoRefresh(load);

  useEffect(() => {
    load(false);
  }, [load]);

  const { employees, machines, orders, tasks, production, incidents } = data;

  const activeOrders = orders.filter(
    (o) => !['COMPLETED', 'DONE', 'CANCELLED'].includes((o.status || '').toUpperCase()),
  );
  const activeRuns = production.filter(
    (p) => !['COMPLETED', 'DONE', 'CANCELLED'].includes((p.status || '').toUpperCase()),
  );
  const openTasks = tasks.filter(
    (t) => !['COMPLETED', 'DONE', 'CANCELLED'].includes((t.status || '').toUpperCase()),
  );
  const openIncidents = incidents.filter(
    (i) => (i.status || '').toUpperCase() !== 'RESOLVED' && (i.status || '').toUpperCase() !== 'CLOSED',
  );
  const machinesOk = machines.filter((m) => (m.health_status || '').toUpperCase() === 'GOOD').length;

  // Production Overview: status mix + quantities (replace with
  // aggregated API data later without touching this layout).
  const prodStatuses = ['PLANNED', 'IN_PROGRESS', 'COMPLETED'];
  const prodCounts = prodStatuses.map(
    (s) => production.filter((p) => (p.status || '').toUpperCase() === s).length,
  );
  const prodMax = Math.max(1, ...prodCounts);
  const qtyTarget = production.reduce((a, p) => a + (p.quantity_target || 0), 0);
  const qtyDone = production.reduce((a, p) => a + (p.quantity_completed || 0), 0);

  // Recent Activity: newest orders + incidents by creation time.
  const activity = [
    ...orders.map((o) => ({
      kind: 'order',
      time: o.created_at,
      text: `Order ${o.order_number || o.id} — ${o.status || 'PENDING'}`,
    })),
    ...incidents.map((i) => ({
      kind: 'incident',
      time: i.created_at,
      text: `${i.incident_type || 'Incident'} — ${i.severity || 'MEDIUM'} (${i.status || 'OPEN'})`,
    })),
  ]
    .filter((a) => a.time)
    .sort((a, b) => new Date(b.time) - new Date(a.time))
    .slice(0, 6);

  return (
    <div className="page">
      <RefreshBar auto={refresher.auto} onAuto={refresher.setAuto} onReload={refresher.refreshNow} refreshing={refresher.refreshing} lastRefresh={refresher.lastRefresh} />
      <div className="page-head" style={{ marginBottom: 12 }}>
        <div>
          <h2 style={{ margin: 0 }}>{bossView ? 'How is my factory doing?' : 'Command Center'}</h2>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button type="button" className={bossView ? 'btn-primary' : 'btn-secondary'} onClick={() => setBossView(true)}>Boss view</button>
          <button type="button" className={!bossView ? 'btn-primary' : 'btn-secondary'} onClick={() => setBossView(false)}>Admin view</button>
        </div>
      </div>
      {failed.length > 0 && !loading && (
        <div className="alert-banner" role="alert">
          Could not reach: {failed.join(', ')}. Showing available data — retry by reloading the page.
        </div>
      )}
      {bossView ? (
        <BossView orders={orders} production={production} incidents={incidents} machines={machines} loading={loading} />
      ) : (
      <>
      {/* KPI strip — live counts from existing list endpoints */}
      <section className="stat-grid" aria-label="Key figures">
        <StatCard label="Active Orders" value={activeOrders.length} sub={`${orders.length} total`} loading={loading} />
        <StatCard label="Production Runs" value={activeRuns.length} sub={`${production.length} total`} loading={loading} />
        <StatCard label="Workforce" value={employees.length} sub="registered employees" loading={loading} />
        <StatCard label="Machine Health" value={`${machinesOk}/${machines.length}`} sub="reporting GOOD" loading={loading} />
        <StatCard label="Active Alerts" value={openIncidents.length} sub="open incidents" loading={loading} />
        <StatCard label="Open Tasks" value={openTasks.length} sub={`${tasks.length} total`} loading={loading} />
      </section>

      <div className="panel-grid">
        {/* Production Overview */}
        <section className="panel">
          <h2>Production Overview</h2>
          {loading ? (
            <p className="muted">Loading production data…</p>
          ) : production.length === 0 ? (
            <p className="muted">No production runs yet. Create orders and runs to populate this view.</p>
          ) : (
            <>
              <div className="bar-rows">
                {prodStatuses.map((s, i) => (
                  <div className="bar-row" key={s}>
                    <span className="bar-label">{s.replace('_', ' ')}</span>
                    <div className="bar-track">
                      <div className="bar-fill" style={{ width: `${(prodCounts[i] / prodMax) * 100}%` }} />
                    </div>
                    <span className="bar-count">{prodCounts[i]}</span>
                  </div>
                ))}
              </div>
              <p className="muted">
                Output {qtyDone} / {qtyTarget} units across {production.length} runs.
              </p>
            </>
          )}
        </section>

        {/* Machine Status Overview */}
        <section className="panel">
          <h2>Machine Status Overview</h2>
          {loading ? (
            <p className="muted">Loading machines…</p>
          ) : machines.length === 0 ? (
            <p className="muted">No machines registered. The IoT simulator seeds demo machines on first run.</p>
          ) : (
            <ul className="machine-list">
              {machines.slice(0, 6).map((m) => (
                <li key={m.id} className="machine-row">
                  <span className="machine-name">{m.name}</span>
                  <span className="machine-meta">{m.machine_type || '—'}</span>
                  <StatusBadge tone={toneForMachine(m)}>{m.health_status || m.status || 'UNKNOWN'}</StatusBadge>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Active Orders */}
        <section className="panel">
          <h2>Active Orders</h2>
          {loading ? (
            <p className="muted">Loading orders…</p>
          ) : activeOrders.length === 0 ? (
            <p className="muted">No active orders. Completed and cancelled orders are hidden here.</p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Order</th>
                  <th>Product</th>
                  <th>Qty</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {activeOrders.slice(0, 5).map((o) => (
                  <tr key={o.id}>
                    <td>{o.order_number || String(o.id).slice(0, 8)}</td>
                    <td>{o.product || '—'}</td>
                    <td>{o.quantity ?? '—'}</td>
                    <td>
                      <StatusBadge tone={toneForOrderStatus(o.status)}>{o.status || 'PENDING'}</StatusBadge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        {/* Active Alerts */}
        <section className="panel">
          <h2>Active Alerts</h2>
          {loading ? (
            <p className="muted">Loading incidents…</p>
          ) : openIncidents.length === 0 ? (
            <p className="muted">No open incidents. The floor is clear.</p>
          ) : (
            <ul className="alert-list">
              {openIncidents.slice(0, 5).map((i) => (
                <li key={i.id} className="alert-row">
                  <StatusBadge tone={toneForIncident(i)}>{i.severity || 'MEDIUM'}</StatusBadge>
                  <span className="alert-text">{i.incident_type || 'Incident'}</span>
                  <span className="muted">{i.status || 'OPEN'}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Employees / Workforce */}
        <section className="panel">
          <h2>Workforce</h2>
          {loading ? (
            <p className="muted">Loading employees…</p>
          ) : employees.length === 0 ? (
            <p className="muted">No employees registered yet.</p>
          ) : (
            <ul className="simple-list">
              {employees.slice(0, 5).map((e) => (
                <li key={e.id}>
                  <span>{e.name}</span>
                  <span className="muted">{e.role || ''} · {e.availability || e.status || ''}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Recent Activity */}
        <section className="panel">
          <h2>Recent Activity</h2>
          {loading ? (
            <p className="muted">Loading activity…</p>
          ) : activity.length === 0 ? (
            <p className="muted">No recent orders or incidents to show.</p>
          ) : (
            <ul className="simple-list">
              {activity.map((a, idx) => (
                <li key={`${a.kind}-${idx}`}>
                  <StatusBadge tone={a.kind === 'incident' ? 'warn' : 'info'}>
                    {a.kind === 'incident' ? 'ALERT' : 'ORDER'}
                  </StatusBadge>
                  <span>{a.text}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
      </>
      )}
    </div>
  );
}
