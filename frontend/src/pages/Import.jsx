import { useState } from 'react';
import { api } from '../services/api';
import StatCard from '../components/StatCard';
import StatusBadge from '../components/StatusBadge';

const TARGETS = ['machines', 'employees', 'orders', 'telemetry'];

export default function Import() {
  const [target, setTarget] = useState('orders');
  const [file, setFile] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [mapping, setMapping] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const handleAnalyze = async () => {
    if (!file) { setError('Choose a .csv or .xlsx file first (max 5 MB, 20k rows).'); return; }
    setBusy(true); setError(''); setResult(null);
    try {
      const res = await api.analyzeImport(target, file);
      setAnalysis(res);
      setMapping(res.mapping || {});
    } catch (err) { setError(err.message || 'Analyze failed'); }
    finally { setBusy(false); }
  };

  const setMap = (col, field) => setMapping((m) => ({ ...m, [col]: field || null }));

  const mappedPreview = () => {
    if (!analysis) return [];
    return (analysis.sample_rows || []).slice(0, 5).map((row) => {
      const out = {};
      for (const [src, fld] of Object.entries(mapping)) if (fld) out[fld] = row[src];
      return out;
    });
  };

  const handleCommit = async () => {
    setBusy(true); setError('');
    try {
      const res = await api.commitImport(target, file, mapping);
      setResult(res);
    } catch (err) { setError(err.message || 'Import failed'); }
    finally { setBusy(false); }
  };

  const unmapped = analysis ? analysis.headers.filter((h) => !mapping[h]) : [];

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>Import Excel / CSV</h2>
          <p className="page-desc">Upload existing files → AI proposes column mapping → you confirm → data is imported. Nothing is written before you confirm.</p>
        </div>
        {analysis && <StatusBadge tone={analysis.source === 'ai' ? 'info' : 'warn'}>{analysis.source === 'ai' ? 'AI mapping' : 'Rule-based mapping'}</StatusBadge>}
      </div>

      <section className="stat-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        <StatCard label="Target" value={target} sub="destination table" loading={false} />
        <StatCard label="Rows" value={analysis ? analysis.row_count : '—'} sub={file ? file.name : 'no file'} loading={busy} />
        <StatCard label="Mapped" value={analysis ? Object.values(mapping).filter(Boolean).length : '—'} sub={`of ${analysis ? analysis.headers.length : '—'} columns`} loading={false} />
        <StatCard label="Unmapped" value={analysis ? unmapped.length : '—'} sub="need review" loading={false} />
      </section>

      {error && <div className="alert-banner" role="alert">{error}</div>}

      <section className="panel">
        <h2>1 · Choose target & file</h2>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <select value={target} onChange={(e) => { setTarget(e.target.value); setAnalysis(null); setResult(null); }}>
            {TARGETS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <input type="file" accept=".csv,.xlsx,.xlsm" onChange={(e) => { setFile(e.target.files?.[0] || null); setAnalysis(null); setResult(null); }} />
          <button type="button" className="btn-primary" onClick={handleAnalyze} disabled={busy || !file}>{busy ? 'Analyzing…' : 'Analyze → propose mapping'}</button>
        </div>
        <p className="muted" style={{ marginTop: 8 }}>Sample files: docs/sample_data/ (messy realistic headers). Max 5 MB · 20,000 rows · .csv/.xlsx only.</p>
      </section>

      {analysis && (
        <>
          <section className="panel">
            <h2>2 · Confirm mapping ({analysis.headers.length} columns)</h2>
            {unmapped.length > 0 && <p className="muted" role="alert">Unmapped columns are highlighted — map them or leave empty to ignore.</p>}
            <table className="data-table">
              <thead><tr><th>Source column</th><th>Target field</th><th>Confidence</th><th>Sample</th></tr></thead>
              <tbody>
                {analysis.headers.map((h) => (
                  <tr key={h} style={!mapping[h] ? { background: 'var(--danger-soft)' } : undefined}>
                    <td className="cell-strong">{h}</td>
                    <td>
                      <select value={mapping[h] || ''} onChange={(e) => setMap(h, e.target.value)}>
                        <option value="">— ignore —</option>
                        {(analysis.target_fields || []).map((f) => <option key={f} value={f}>{f}</option>)}
                      </select>
                    </td>
                    <td className="cell-mono">{(analysis.confidence?.[h] ?? 0).toFixed(2)}</td>
                    <td className="muted">{String(analysis.sample_rows?.[0]?.[h] ?? '—').slice(0, 40)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="panel">
            <h2>3 · Preview (5 mapped rows)</h2>
            <pre className="muted" style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(mappedPreview(), null, 1)}</pre>
            <div style={{ marginTop: 12 }}>
              <button type="button" className="btn-primary" onClick={handleCommit} disabled={busy}>{busy ? 'Importing…' : `Confirm & import ${analysis.row_count} rows`}</button>
            </div>
          </section>
        </>
      )}

      {result && (
        <section className="panel" role="status">
          <h2>Result</h2>
          <p className="muted">Inserted <b>{result.inserted}</b> · skipped duplicates <b>{result.skipped_duplicates}</b> · failed <b>{result.failed}</b></p>
          {result.note && <p className="muted">{result.note}</p>}
          {(result.errors || []).length > 0 && (
            <ul className="form-errors">{result.errors.map((e, i) => <li key={i}>Row {e.row}: {e.error}</li>)}</ul>
          )}
        </section>
      )}
    </div>
  );
}
