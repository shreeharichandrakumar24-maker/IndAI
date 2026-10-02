import { useEffect, useState } from 'react';
import { api } from '../services/api';
import StatCard from '../components/StatCard';
import StatusBadge from '../components/StatusBadge';

function toneForRisk(level) {
  if (level === 'HIGH') return 'bad';
  if (level === 'MEDIUM') return 'warn';
  return 'ok';
}

// What-if simulator (F9): deterministic projection + AI narrative.
// Simulations NEVER write: applying for real goes through the normal
// endpoints (order/task updates) only after an explicit Apply click.
export default function Simulate() {
  const [scenario, setScenario] = useState('DELAY_ORDER');
  const [orders, setOrders] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [machines, setMachines] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [form, setForm] = useState({ order_id: '', days: 3, incident_id: '', task_id: '', employee_id: '', machine_id: '' });
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [applyMsg, setApplyMsg] = useState('');
  const [applying, setApplying] = useState(false);

  useEffect(() => {
    Promise.allSettled([api.orders(), api.tasks(), api.employees().catch(() => []),
      api.machines().catch(() => []), api.incidents().catch(() => [])]).then(
      ([o, t, e, m, i]) => {
        if (o.status === 'fulfilled') setOrders(o.value || []);
        if (t.status === 'fulfilled') setTasks(t.value || []);
        if (e.status === 'fulfilled') setEmployees(e.value || []);
        if (m.status === 'fulfilled') setMachines(m.value || []);
        if (i.status === 'fulfilled') setIncidents((i.value || []).filter((x) => (x.status || 'OPEN') !== 'RESOLVED'));
      });
  }, []);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const run = async () => {
    setBusy(true);
    setError('');
    setResult(null);
    setApplyMsg('');
    try {
      const payload = { scenario_type: scenario };
      if (scenario === 'DELAY_ORDER') {
        if (!form.order_id) throw new Error('Pick an order');
        payload.order_id = form.order_id;
        payload.days = Number(form.days) || 0;
      } else if (scenario === 'RESOLVE_INCIDENT') {
        if (!form.incident_id) throw new Error('Pick an incident');
        payload.incident_id = form.incident_id;
      } else {
        if (!form.task_id) throw new Error('Pick a task');
        payload.task_id = form.task_id;
        if (form.employee_id) payload.employee_id = form.employee_id;
        if (form.machine_id) payload.machine_id = form.machine_id;
        if (!form.employee_id && !form.machine_id) throw new Error('Pick a worker and/or machine');
      }
      setResult(await api.simulate(payload));
    } catch (err) {
      setError(err.message || 'Simulation failed');
    } finally {
      setBusy(false);
    }
  };

  const applyDelay = async (row) => {
    setApplying(true);
    setApplyMsg('');
    try {
      await api.updateOrder(row.order_id, { deadline: row.new_deadline });
      try {
        await api.memoryLog({
          title: `Simulation applied: delayed ${row.order_number || 'order'}`,
          event_type: 'SIMULATION_APPLIED',
          description: `What-if DELAY_ORDER applied: ${row.old_risk} → ${row.new_risk}.`,
          order_id: row.order_id,
          metadata_: { scenario: 'DELAY_ORDER', old_risk: row.old_risk, new_risk: row.new_risk },
        });
      } catch { /* record-only */ }
      setApplyMsg(`Applied: order deadline moved. See Orders. (Simulation itself wrote nothing.)`);
    } catch (err) {
      setApplyMsg(`Apply failed: ${err.message}`);
    } finally {
      setApplying(false);
    }
  };

  const applyReassign = async () => {
    const f = result?.feasibility;
    if (!f || !f.ok) return;
    setApplying(true);
    setApplyMsg('');
    try {
      const body = {};
      if (f.employee_id) body.employee_id = f.employee_id;
      if (f.machine_id) body.machine_id = f.machine_id;
      await api.updateTask(form.task_id, body);
      try {
        await api.memoryLog({
          title: 'Simulation applied: task reassigned',
          event_type: 'SIMULATION_APPLIED',
          description: `What-if REASSIGN_TASK applied: ${(f.verdicts || []).join(' ')}`.slice(0, 500),
          task_id: form.task_id,
          machine_id: f.machine_id || null,
          metadata_: { scenario: 'REASSIGN_TASK' },
        });
      } catch { /* record-only */ }
      setApplyMsg('Applied: task reassigned. See Tasks.');
    } catch (err) {
      setApplyMsg(`Apply failed: ${err.message}`);
    } finally {
      setApplying(false);
    }
  };

  const changed = (result?.affected_orders || []).filter((r) => r.old_risk !== r.new_risk).length;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>What-if simulator</h2>
          <p className="page-desc">Project a decision before making it. Simulations never change data — Apply does, through the normal pages.</p>
        </div>
        {result && <StatusBadge tone="warn">display-only projection</StatusBadge>}
      </div>

      <section className="stat-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
        <StatCard label="Orders affected" value={result ? result.affected_orders.length : '—'} sub="in projection" loading={false} />
        <StatCard label="Risk changed" value={result ? changed : '—'} sub="orders" loading={false} />
        <StatCard label="AI narrative" value={result ? (result.narrative ? 'yes' : 'numbers only') : '—'} sub={result && !result.narrative ? 'key missing' : ''} loading={false} />
      </section>

      {error && <div className="alert-banner" role="alert">{error}</div>}
      {applyMsg && <div className="panel" role="status"><p className="muted">{applyMsg}</p></div>}

      <section className="panel">
        <h2>1 · Pick a scenario</h2>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
          {[['DELAY_ORDER', 'Delay an order'], ['RESOLVE_INCIDENT', 'Fix a breakdown'], ['REASSIGN_TASK', 'Move a task']].map(([v, label]) => (
            <button key={v} type="button" className={scenario === v ? 'btn-primary' : 'btn-secondary'} onClick={() => { setScenario(v); setResult(null); }}>{label}</button>
          ))}
        </div>
        {scenario === 'DELAY_ORDER' && (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <select value={form.order_id} onChange={(e) => set('order_id', e.target.value)}>
              <option value="">— Order —</option>
              {orders.map((o) => <option key={o.id} value={o.id}>{o.order_number} ({o.status})</option>)}
            </select>
            <label>Days <input type="number" value={form.days} onChange={(e) => set('days', e.target.value)} style={{ width: 90 }} /></label>
          </div>
        )}
        {scenario === 'RESOLVE_INCIDENT' && (
          <select value={form.incident_id} onChange={(e) => set('incident_id', e.target.value)}>
            <option value="">— Open incident —</option>
            {incidents.map((i) => <option key={i.id} value={i.id}>{i.incident_type} · {i.severity}</option>)}
          </select>
        )}
        {scenario === 'REASSIGN_TASK' && (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <select value={form.task_id} onChange={(e) => set('task_id', e.target.value)}>
              <option value="">— Task —</option>
              {tasks.map((t) => <option key={t.id} value={t.id}>{t.name} ({t.status})</option>)}
            </select>
            <select value={form.employee_id} onChange={(e) => set('employee_id', e.target.value)}>
              <option value="">— Worker (optional) —</option>
              {employees.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
            </select>
            <select value={form.machine_id} onChange={(e) => set('machine_id', e.target.value)}>
              <option value="">— Machine (optional) —</option>
              {machines.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </div>
        )}
        <div style={{ marginTop: 12 }}>
          <button type="button" className="btn-primary" onClick={run} disabled={busy}>{busy ? 'Projecting…' : 'Run projection →'}</button>
        </div>
      </section>

      {result && (
        <>
          <section className="panel">
            <h2>2 · Projection</h2>
            {(result.assumptions || []).map((a, i) => <p className="muted" key={i}>Assumes: {a}</p>)}
            {(result.warnings || []).map((w, i) => <p className="muted" key={i}>⚠ {w}</p>)}
            {result.feasibility && (
              <p className="muted">
                Feasible: <b>{result.feasibility.ok ? 'yes' : 'no'}</b> — {(result.feasibility.verdicts || []).join(' ')}
              </p>
            )}
            <table className="data-table">
              <thead><tr><th>Order</th><th>Before</th><th>After</th><th>Change</th></tr></thead>
              <tbody>
                {result.affected_orders.length === 0 && <tr><td colSpan={4} className="muted">No orders affected.</td></tr>}
                {result.affected_orders.map((r) => (
                  <tr key={r.order_id}>
                    <td className="cell-strong">{r.order_number || r.order_id.slice(0, 8)}</td>
                    <td><StatusBadge tone={toneForRisk(r.old_risk)}>{r.old_risk}</StatusBadge></td>
                    <td><StatusBadge tone={toneForRisk(r.new_risk)}>{r.new_risk}</StatusBadge></td>
                    <td className="muted">{r.old_risk === r.new_risk ? 'no change' : `${r.old_risk} → ${r.new_risk}`}{r.delta_hours ? ` (${r.delta_hours}h)` : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {result.narrative && <p style={{ marginTop: 8 }}><b>Assistant:</b> {result.narrative}</p>}
          </section>

          <section className="panel">
            <h2>3 · Apply for real (optional)</h2>
            {scenario === 'DELAY_ORDER' && result.affected_orders.length > 0 && (
              <button type="button" className="btn-primary" disabled={applying} onClick={() => applyDelay(result.affected_orders[0])}>
                {applying ? 'Applying…' : 'Apply deadline change'}
              </button>
            )}
            {scenario === 'REASSIGN_TASK' && result.feasibility?.ok && (
              <button type="button" className="btn-primary" disabled={applying} onClick={applyReassign}>
                {applying ? 'Applying…' : 'Apply reassignment'}
              </button>
            )}
            {scenario === 'RESOLVE_INCIDENT' && (
              <p className="muted">Breakdowns resolve through the incident workflow (maintenance + normal readings) — open the Incidents page. No shortcut applied.</p>
            )}
          </section>
        </>
      )}
    </div>
  );
}
