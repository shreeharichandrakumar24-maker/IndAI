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
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const resetAfterInput = () => { setAnalysis(null); setPreview(null); setResult(null); };

  const handleAnalyze = async () => {
    if (!file) { setError('Choose a .csv or .xlsx file first (max 5 MB, 20k rows).'); return; }
    setBusy(true); setError(''); setResult(null); setPreview(null);
    try {
      const res = await api.analyzeImport(target, file);
      setAnalysis(res);
      setMapping(res.mapping || {});
    } catch (err) { setError(err.message || 'Analyze failed'); }
    finally { setBusy(false); }
  };

  const setMap = (col, field) => {
    setMapping((m) => ({ ...m, [col]: field || null }));
    setPreview(null);
  };

  const handlePreview = async () => {
    if (!file || !analysis) return;
    setPreviewBusy(true); setError('');
    try {
      const res = await api.previewImport(target, file, mapping);
      setPreview(res);
    } catch (err) { setError(err.message || 'Preview failed'); }
    finally { setPreviewBusy(false); }
  };

  const handleConfirm = async () => {
    setConfirmBusy(true); setError('');
    try {
      const res = await api.confirmImport(target, file, mapping);
      setResult(res);
      setPreview(null);
    } catch (err) { setError(err.message || 'Import failed'); }
    finally { setConfirmBusy(false); }
  };

  const unmapped = analysis ? analysis.headers.filter((h) => !mapping[h]) : [];
  const reasonByCol = {};
  for (const d of (analysis?.proposed_mapping || [])) {
    if (d && d.source_column) reasonByCol[d.source_column] = d.reason || '';
  }

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
          <select value={target} onChange={(e) => { setTarget(e.target.value); resetAfterInput(); }}>
            {TARGETS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <input type="file" accept=".csv,.xlsx,.xlsm" onChange={(e) => { setFile(e.target.files?.[0] || null); resetAfterInput(); }} />
          <button type="button" className="btn-primary" onClick={handleAnalyze} disabled={busy || !file}>{busy ? 'Analyzing…' : 'Analyze → propose mapping'}</button>
        </div>
        <p className="muted" style={{ marginTop: 8 }}>Sample files: docs/sample_data/ (messy realistic headers). Max 5 MB · 20,000 rows · .csv/.xlsx only.</p>
        {(analysis?.warnings || []).length > 0 && (
          <ul className="muted" style={{ marginTop: 8 }}>
            {(analysis.warnings || []).slice(0, 6).map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        )}
      </section>

      {analysis && (
        <>
          <section className="panel">
            <h2>2 · Confirm mapping ({analysis.headers.length} columns)</h2>
            {unmapped.length > 0 && <p className="muted" role="alert">Unmapped columns are highlighted — map them or leave empty to ignore.</p>}
            <table className="data-table">
              <thead><tr><th>Source column</th><th>Proposed field</th><th>Confidence</th><th>Note</th><th>Sample</th><th>Action</th></tr></thead>
              <tbody>
                {analysis.headers.map((h) => (
                  <tr key={h} style={!mapping[h] ? { background: 'var(--danger-soft)' } : undefined}>
                    <td className="cell-strong">{h}</td>
                    <td className="cell-mono">{mapping[h] || '— ignore —'}</td>
                    <td className="cell-mono">{(analysis.confidence?.[h] ?? 0).toFixed(2)}</td>
                    <td className="muted">{reasonByCol[h] || '—'}</td>
                    <td className="muted">{String(analysis.sample_rows?.[0]?.[h] ?? '—').slice(0, 40)}</td>
                    <td>
                      <select value={mapping[h] || ''} onChange={(e) => setMap(h, e.target.value)}>
                        <option value="">— ignore —</option>
                        {(analysis.target_fields || []).map((f) => <option key={f} value={f}>{f}</option>)}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="panel">
            <h2>3 · Preview validation (no data written)</h2>
            <div style={{ marginBottom: 12 }}>
              <button type="button" className="btn-secondary" onClick={handlePreview} disabled={previewBusy || !file}>
                {previewBusy ? 'Validating…' : 'Preview validation'}
              </button>
            </div>
            {preview && (
              <>
                <p className="muted" role="status">
                  Valid <b>{preview.valid_count}</b> · invalid <b>{preview.invalid_count}</b> · duplicates <b>{preview.duplicate_count}</b> · of {preview.row_count} rows
                </p>
                {(preview.warnings || []).length > 0 && (
                  <ul className="muted">{preview.warnings.slice(0, 6).map((w, i) => <li key={i}>{w}</li>)}</ul>
                )}
                {(preview.invalid_rows || []).length > 0 && (
                  <>
                    <h3 className="section-title">Invalid rows (will be skipped)</h3>
                    <ul className="form-errors">{preview.invalid_rows.map((e, i) => <li key={i}>Row {e.row}: {e.error}</li>)}</ul>
                  </>
                )}
                {(preview.duplicate_rows || []).length > 0 && (
                  <>
                    <h3 className="section-title">Duplicates (already exist — will be skipped, never overwritten)</h3>
                    <ul className="muted">{preview.duplicate_rows.map((e, i) => <li key={i}>Row {e.row}: {e.key}</li>)}</ul>
                  </>
                )}
                {(preview.valid_rows || []).length > 0 && (
                  <>
                    <h3 className="section-title">Valid rows (first {Math.min(preview.valid_rows.length, 25)})</h3>
                    <pre className="muted" style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(preview.valid_rows.slice(0, 5), null, 1)}</pre>
                  </>
                )}
              </>
            )}
          </section>

          <section className="panel">
            <h2>4 · Confirm & import (this writes to the database)</h2>
            <p className="muted">Only this button writes data — everything above is analysis only. Invalid and duplicate rows are skipped, never overwritten.</p>
            <div style={{ marginTop: 12 }}>
              <button type="button" className="btn-primary" onClick={handleConfirm} disabled={confirmBusy}>
                {confirmBusy ? 'Importing…' : `Confirm & import${preview ? ` ${preview.valid_count} valid rows` : ` ${analysis.row_count} rows`}`}
              </button>
            </div>
          </section>
        </>
      )}

      {result && (
        <section className="panel" role="status">
          <h2>Result</h2>
          <p className="muted">
            Imported <b>{result.imported_count ?? result.inserted}</b> · Skipped <b>{result.skipped_count ?? result.skipped_duplicates}</b> · failed <b>{result.failed}</b>
          </p>
          <p className="muted">Open the {target} page to see the new rows.</p>
          {result.note && <p className="muted">{result.note}</p>}
          {(result.errors || []).length > 0 && (
            <ul className="form-errors">{result.errors.map((e, i) => <li key={i}>Row {e.row}: {e.error}</li>)}</ul>
          )}
        </section>
      )}
    </div>
  );
}
