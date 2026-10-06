import { useState } from 'react';
import { api } from '../services/api';
import StatCard from '../components/StatCard';
import StatusBadge from '../components/StatusBadge';

// What-if simulator: "Ask in plain words" ONLY (employee leave / machine downtime).
// Strictly read-only: POST /api/what-if/simulate SELECTs and builds plain dicts,
// commits nothing. Factory scoping rides on the shared request() helper
// (X-Factory-Id header), exactly as before.
export default function Simulate() {
  const [nlText, setNlText] = useState('');
  const [nlResult, setNlResult] = useState(null);
  const [nlBusy, setNlBusy] = useState(false);
  const [nlError, setNlError] = useState('');

  const runNl = async () => {
    const text = nlText.trim();
    if (!text) {
      setNlError('Describe a scenario first.');
      return;
    }
    setNlBusy(true);
    setNlError('');
    setNlResult(null);
    try {
      setNlResult(await api.whatIf(text));
    } catch (err) {
      setNlError(err.message || 'Simulation failed');
    } finally {
      setNlBusy(false);
    }
  };

  const tryAnother = () => {
    setNlText('');
    setNlResult(null);
    setNlError('');
  };

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>WHAT IF?</h2>
          <p className="page-desc">Ask in plain words. Simulations never change data.</p>
        </div>
        {nlResult && <StatusBadge tone="warn">simulation only — no data changed</StatusBadge>}
      </div>

      <section className="panel">
        <h2>Ask in plain words</h2>
        <textarea
          value={nlText}
          onChange={(e) => setNlText(e.target.value)}
          placeholder="What if John is on leave for 2 days?"
          rows={3}
          style={{ width: '100%', maxWidth: 640 }}
          disabled={nlBusy}
          aria-label="What-if scenario in plain words"
        />
        <p className="muted">
          Example: &ldquo;What if John is on leave for 2 days?&rdquo;
          &ldquo;What if CNC Machine 2 is unavailable for 4 hours?&rdquo;
        </p>
        {nlError && <div className="alert-banner" role="alert">{nlError}</div>}
        <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
          <button type="button" className="btn-primary" onClick={runNl} disabled={nlBusy}>
            {nlBusy ? 'Analyzing factory impact…' : 'Simulate'}
          </button>
          {(nlResult || nlText) && (
            <button type="button" className="btn-secondary" onClick={tryAnother} disabled={nlBusy}>
              Try Another
            </button>
          )}
        </div>
      </section>

      {!nlResult && !nlBusy && !nlError && (
        <p className="muted">No simulation yet — describe a scenario above and press Simulate.</p>
      )}

      {nlResult && (
        <section className="panel">
          <h2>SCENARIO <StatusBadge tone="warn">simulation only — no data changed</StatusBadge></h2>
          <p>
            <b>{nlResult.scenario.entity_name}</b>
            {' '}(simulated {nlResult.scenario.duration_hours}h {nlResult.scenario.reason || nlResult.scenario.type})
          </p>
          <p className="muted">{nlResult.summary}</p>

          <h3 className="section-title">IMPACT</h3>
          <section className="stat-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
            <StatCard label="Affected Tasks" value={nlResult.impact.affected_tasks} sub="open tasks" loading={false} />
            <StatCard label="Affected Orders" value={nlResult.impact.affected_orders} sub="orders" loading={false} />
            <StatCard label="Affected Production" value={nlResult.impact.affected_production_runs} sub="runs" loading={false} />
            <StatCard label="Estimated Delay" value={`${nlResult.impact.estimated_delay_hours}h`} sub="if uncovered" loading={false} />
          </section>

          <h3 className="section-title">AFFECTED TASKS</h3>
          {(nlResult.affected_tasks || []).length === 0 && <p className="muted">No open work affected.</p>}
          <ul>
            {(nlResult.affected_tasks || []).map((t) => (
              <li key={t.id}>{t.name} <span className="muted">({t.status}, {Math.round((t.current_progress || 0) * 100)}%)</span></li>
            ))}
          </ul>

          <h3 className="section-title">AFFECTED ORDERS</h3>
          {(nlResult.affected_order_ids || []).length === 0 && <p className="muted">No orders affected.</p>}
          <ul>
            {(nlResult.affected_order_ids || []).map((id) => (
              <li key={id} className="cell-mono">{String(id).slice(0, 8)}</li>
            ))}
          </ul>

          <h3 className="section-title">ALTERNATIVES</h3>
          {(nlResult.alternatives || []).length === 0 && <p className="muted">No cover available.</p>}
          {(nlResult.alternatives || []).length > 0 && (
            <ul>
              {nlResult.alternatives.map((a) => (
                <li key={a.id}><b>{a.name}</b> <span className="muted">— {a.reason}</span></li>
              ))}
            </ul>
          )}

          <h3 className="section-title">RECOMMENDATION</h3>
          <p>{nlResult.recommendation}</p>

          <h3 className="section-title">ASSUMPTIONS</h3>
          {(nlResult.assumptions || []).length === 0 && <p className="muted">—</p>}
          <ul>
            {(nlResult.assumptions || []).map((a, i) => (
              <li key={i} className="muted">Assumes: {a}</li>
            ))}
          </ul>

          {nlResult.narrative && <p><b>Assistant:</b> {nlResult.narrative}</p>}
        </section>
      )}
    </div>
  );
}
