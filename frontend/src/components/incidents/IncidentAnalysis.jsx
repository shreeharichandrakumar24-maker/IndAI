import { useState } from 'react';
import { api } from '../../services/api';
import StatusBadge from '../StatusBadge';

// AI analysis section inside IncidentDetails (Phase E).
// Nothing is applied without an explicit Approve/Reject click.
function toneForRisk(level) {
  const l = (level || '').toUpperCase();
  if (l === 'HIGH') return 'bad';
  if (l === 'MEDIUM') return 'warn';
  if (l === 'LOW') return 'ok';
  return 'neutral';
}

export default function IncidentAnalysis({ incident, onChanged }) {
  const [analysis, setAnalysis] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [aiDown, setAiDown] = useState(false);
  const [notes, setNotes] = useState({});
  const [deciding, setDeciding] = useState('');

  const runAnalysis = async () => {
    setBusy(true);
    setError('');
    setAiDown(false);
    try {
      const res = await api.analyzeIncident(incident.id);
      setAnalysis(res);
      if (onChanged) onChanged();
    } catch (err) {
      const msg = err.message || 'Analysis failed';
      if (msg.includes('503') || msg.toLowerCase().includes('ai unavailable')) setAiDown(true);
      setError(msg);
    } finally {
      setBusy(false);
    }
  };

  const decide = async (rec, decision) => {
    setDeciding(rec.id + decision);
    setError('');
    try {
      await api.decideRecommendation(rec.id, decision, notes[rec.id] || '');
      // Refresh: re-list recommendations for this incident.
      const list = await api.recommendations(incident.id);
      setAnalysis((a) => (a ? { ...a, recommendations: list } : a));
      if (onChanged) onChanged();
    } catch (err) {
      setError(err.message || 'Decision failed');
    } finally {
      setDeciding('');
    }
  };

  const detByOrder = Object.fromEntries((analysis?.deterministic_risk || []).map((d) => [d.order_id, d]));

  return (
    <div>
      <h3 className="section-title">AI analysis</h3>
      {!analysis ? (
        <>
          <p className="muted">Root-cause explanation, order-risk prediction and recommended actions. AI output is labeled; deterministic facts stay labeled deterministic.</p>
          <button type="button" className="btn-primary" onClick={runAnalysis} disabled={busy}>{busy ? 'Analyzing…' : '✦ Analyze with AI'}</button>
        </>
      ) : (
        <button type="button" className="btn-secondary" onClick={runAnalysis} disabled={busy}>{busy ? 'Re-analyzing…' : '↻ Re-analyze'}</button>
      )}
      {error && <p className="form-errors" role="alert" style={{ marginTop: 8 }}>{error}</p>}
      {aiDown && <p className="muted" role="status">AI unavailable — showing deterministic risk and snapshot facts only (no AI guesses).</p>}

      {analysis && (
        <div style={{ marginTop: 12 }}>
          <h4 className="section-title">Root cause <StatusBadge tone="info">AI</StatusBadge></h4>
          <p><b>{analysis.root_cause?.summary}</b></p>
          {(analysis.root_cause?.contributing_factors || []).length > 0 && (
            <ul className="task-list">{analysis.root_cause.contributing_factors.map((f, i) => <li key={i} className="task-row"><span className="task-meta">{f}</span></li>)}</ul>
          )}
          <p className="muted">Confidence: <span className="cell-mono">{analysis.root_cause?.confidence ?? '—'}</span></p>

          <h4 className="section-title">Order risk</h4>
          {(analysis.order_risk_ai || []).length === 0 && <p className="muted">No affected orders in snapshot — insufficient data.</p>}
          {(analysis.order_risk_ai || []).map((r) => {
            const det = detByOrder[r.order_id];
            return (
              <div key={r.order_id} className="panel" style={{ marginTop: 8 }}>
                <p><span className="cell-mono">{r.order_id.slice(0, 8)}</span> <StatusBadge tone={toneForRisk(r.risk_level)}>AI: {r.risk_level}</StatusBadge>{' '}
                  {det && <StatusBadge tone={toneForRisk(det.risk_level)}>Deterministic: {det.risk_level}</StatusBadge>}</p>
                <p className="muted">AI: {r.reason || '—'}{r.estimated_delay_hours != null ? ` · ~${r.estimated_delay_hours}h delay` : ''}</p>
                {det && <p className="muted">Deterministic: {det.reason} <span className="cell-mono">{JSON.stringify(det.numbers)}</span></p>}
              </div>
            );
          })}

          <h4 className="section-title">Recommendations</h4>
          {(analysis.recommendations || []).length === 0 && <p className="muted">No recommendations saved yet.</p>}
          {(analysis.recommendations || []).map((rec) => (
            <div key={rec.id} className="panel" style={{ marginTop: 8 }}>
              <p><b>{rec.recommendation}</b></p>
              <p className="muted"><StatusBadge tone={rec.status === 'PENDING' ? 'warn' : rec.status === 'APPROVED' ? 'ok' : 'neutral'}>{rec.status}</StatusBadge> <span className="cell-mono">{rec.recommendation_type}</span> · confidence {rec.confidence ?? '—'}</p>
              {rec.status === 'PENDING' ? (
                <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                  <input
                    placeholder="Optional note"
                    value={notes[rec.id] || ''}
                    onChange={(e) => setNotes((n) => ({ ...n, [rec.id]: e.target.value }))}
                    style={{ flex: 1, minWidth: 160 }}
                  />
                  <button type="button" className="btn-primary" disabled={!!deciding} onClick={() => decide(rec, 'APPROVED')}>{deciding === rec.id + 'APPROVED' ? 'Saving…' : 'Approve'}</button>
                  <button type="button" className="btn-secondary" disabled={!!deciding} onClick={() => decide(rec, 'REJECTED')}>{deciding === rec.id + 'REJECTED' ? 'Saving…' : 'Reject'}</button>
                </div>
              ) : (
                <p className="muted">Decision recorded → saved to Factory Memory. {rec.status === 'APPROVED' && rec.recommendation_type === 'SCHEDULE_MAINTENANCE' ? 'A PENDING maintenance row was created.' : 'No data was changed (record-only).'}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
