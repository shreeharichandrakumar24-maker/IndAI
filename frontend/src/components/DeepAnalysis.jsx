import { useState } from 'react';
import { api } from '../services/api';
import StatusBadge from './StatusBadge';

// Shared deep-analysis section for Machine and Order detail modals (F7).
// Correlates telemetry + tasks + orders + maintenance + memory for one scope.
// Display-only: no writes, AI-labeled, graceful when the key is missing.
export default function DeepAnalysis({ scope }) {
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const run = async () => {
    setBusy(true);
    setError('');
    try {
      const res = await api.rootCause(scope);
      setResult(res);
    } catch (err) {
      setError(err.message || 'Deep analysis failed');
    } finally {
      setBusy(false);
    }
  };

  const aiDown = error.includes('503') || error.toLowerCase().includes('ai unavailable');

  return (
    <div>
      <h3 className="section-title">Deep analysis <StatusBadge tone="info">AI</StatusBadge></h3>
      {!result ? (
        <>
          <p className="muted">Correlates sensors, tasks, orders, repairs and past events to find the root cause.</p>
          <button type="button" className="btn-primary" onClick={run} disabled={busy}>
            {busy ? 'Analyzing…' : '🔍 Run deep analysis'}
          </button>
        </>
      ) : (
        <button type="button" className="btn-secondary" onClick={run} disabled={busy}>
          {busy ? 'Re-analyzing…' : '↻ Re-analyze'}
        </button>
      )}
      {error && (
        <>
          <p className="form-errors" role="alert" style={{ marginTop: 8 }}>{error}</p>
          {aiDown && (
            <p className="muted" role="status">AI unavailable — configure the LLM key to enable cross-system diagnosis. The tables above still show every underlying fact.</p>
          )}
        </>
      )}
      {result && (
        <div style={{ marginTop: 12 }}>
          <p><b>{result.primary_cause}</b></p>
          <p className="muted">Confidence: <span className="cell-mono">{result.confidence ?? '—'}</span></p>
          {(result.evidence || []).length > 0 && (
            <>
              <h4 className="section-title">Evidence by system</h4>
              <ul className="task-list">
                {result.evidence.map((e, i) => (
                  <li key={i} className="task-row">
                    <div className="task-main">
                      <span className="cell-strong">{e.system}</span>
                      <span className="task-meta">{e.fact}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
          {result.snapshot_facts && (
            <p className="muted">
              Snapshot: {result.snapshot_facts.incidents} incident(s) · {result.snapshot_facts.open_tasks} task row(s) in scope.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
