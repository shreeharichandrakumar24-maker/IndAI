import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../services/api';
import StatusBadge from '../components/StatusBadge';

const INDUSTRIES = [
  'CNC / Mechanical', 'Automotive Components', 'Sheet Metal / Fabrication',
  'Electronics Assembly', 'Plastics / Injection Molding', 'Food & Beverage',
  'Textiles / Apparel', 'Pharmaceutical', 'Packaging', 'Other',
];

const STEPS = [
  { key: 'company', label: 'Company / Industry' },
  { key: 'employees', label: 'Employees' },
  { key: 'machines', label: 'Machines / Equipment' },
  { key: 'production', label: 'Production' },
  { key: 'orders', label: 'Orders / Customers' },
  { key: 'maintenance', label: 'Maintenance History' },
  { key: 'thresholds', label: 'IoT Thresholds' },
  { key: 'ai_preferences', label: 'AI Preferences' },
];

const PRIORITIES = ['PRODUCTION_CONTINUITY', 'DELIVERY_DEADLINES', 'MACHINE_HEALTH', 'MAINTENANCE_COST',
  'PRODUCTION_COST', 'QUALITY', 'WORKFORCE_UTILIZATION', 'CUSTOMER_PRIORITY'];
const STYLES = ['ACTIONABLE', 'BALANCED', 'DETAILED'];
const RISKS = ['CONSERVATIVE', 'BALANCED', 'AGGRESSIVE'];
const DEFAULT_THRESHOLDS = { temp_max: 85, vibration_max: 5, current_max: 10, rpm_min: 1300 };

const CSV_SPECS = {
  employees: { headers: ['employee_id', 'name', 'role', 'department', 'skills', 'certifications', 'shift', 'experience_years'], required: ['name', 'role'] },
  machines: { headers: ['machine_id', 'machine_name', 'type', 'location', 'department', 'criticality', 'status'], required: ['machine_id', 'machine_name'] },
  orders: { headers: ['order_id', 'customer', 'product', 'quantity', 'priority', 'deadline'], required: ['order_id'] },
  maintenance: { headers: ['maintenance_id', 'machine_id', 'date', 'issue', 'action', 'resolution', 'technician', 'downtime_hours', 'status'], required: ['machine_id', 'issue', 'date'] },
};

// --- tiny CSV parser (preview only; the backend validates again) ---
function splitCsvLine(line) {
  const out = [];
  let cur = '';
  let quoted = false;
  for (let i = 0; i < line.length; i += 1) {
    const c = line[i];
    if (quoted) {
      if (c === '"' && line[i + 1] === '"') { cur += '"'; i += 1; }
      else if (c === '"') quoted = false;
      else cur += c;
    } else if (c === '"') quoted = true;
    else if (c === ',') { out.push(cur); cur = ''; }
    else cur += c;
  }
  out.push(cur);
  return out.map((s) => s.trim());
}

function parseCsv(text) {
  const lines = String(text || '').split(/\r?\n/).filter((l) => l.trim() !== '');
  if (lines.length < 2) return { headers: [], rows: [], errors: ['CSV needs a header row and at least one data row.'] };
  const headers = splitCsvLine(lines[0]).map((h) => h.toLowerCase());
  const rows = lines.slice(1).map((line) => {
    const cells = splitCsvLine(line);
    const obj = {};
    headers.forEach((h, i) => { obj[h] = cells[i] ?? ''; });
    return obj;
  });
  return { headers, rows, errors: [] };
}

function validateRows(section, rows) {
  const spec = CSV_SPECS[section];
  const errors = [];
  const ok = [];
  rows.forEach((r, i) => {
    const missing = (spec.required || []).filter((c) => !String(r[c] ?? '').trim());
    if (missing.length) errors.push({ row: i + 1, message: `missing ${missing.join(', ')}` });
    else ok.push(r);
  });
  return { errors, ok };
}

const EMPTY = {
  company: { name: '', industry: '', products: '', employee_count: '' },
  production: { processes: [], shifts: [], capacity: { value: '', unit: 'units/day' } },
  thresholds: { mode: 'default', default: { ...DEFAULT_THRESHOLDS }, by_type: {} },
  ai_preferences: { primary_priority: 'PRODUCTION_CONTINUITY', secondary_priorities: [], recommendation_style: 'BALANCED', risk_tolerance: 'BALANCED' },
};

export default function FactoryOnboarding({ onDone, factoryName }) {
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState(0);
  const [review, setReview] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.onboardingState();
      setState(res.onboarding);
      const cur = Number(res.onboarding?.current_step || 1) - 1;
      setStep(Math.min(Math.max(cur, 0), 7));
    } catch (err) {
      setError(err.message || 'Failed to load onboarding state.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const sections = state?.sections || {};
  const sectionData = (key) => sections[key]?.data || {};
  const sectionStatus = (key) => sections[key]?.status || 'PENDING';

  const applyState = (res) => {
    if (res?.onboarding) setState(res.onboarding);
  };

  const saveSection = async (key, body, { advance = true } = {}) => {
    setBusy(true); setError(''); setNotice('');
    try {
      const res = await api.saveOnboardingSection(key, body);
      applyState(res);
      if (advance) next();
      else setNotice('Saved.');
    } catch (err) {
      const detail = err?.message || 'Save failed.';
      setError(detail);
    } finally {
      setBusy(false);
    }
  };

  const markNotAvailable = async (key) => {
    setBusy(true); setError(''); setNotice('');
    try {
      const res = await api.onboardingNotAvailable(key);
      applyState(res);
    } catch (err) {
      setError(err?.message || 'Failed.');
    } finally {
      setBusy(false);
    }
  };

  const next = () => setStep((s) => Math.min(s + 1, 7));
  const back = () => setStep((s) => Math.max(s - 1, 0));

  const goReview = () => setReview(true);

  const handleComplete = async () => {
    setBusy(true); setError('');
    try {
      await api.completeOnboarding();
      onDone();
    } catch (err) {
      setError(err?.message || 'Complete setup failed.');
      setReview(false);
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <div className="page"><p className="muted">Loading onboarding…</p></div>;
  }

  const current = STEPS[step];

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>Set up {factoryName || 'your factory'}</h2>
          <p className="page-desc">Eight short steps. Progress saves as you go — refreshing the page never loses it.</p>
        </div>
        <StatusBadge tone={state?.status === 'COMPLETE' ? 'ok' : 'warn'}>
          {review ? 'REVIEW' : `STEP ${step + 1} / 8`} · {state?.status || 'DRAFT'}
        </StatusBadge>
      </div>

      {error && <div className="alert-banner" role="alert">{error}</div>}
      {notice && <div className="panel" role="status"><p className="muted">{notice}</p></div>}

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 16 }}>
        {STEPS.map((s, i) => {
          const st = sectionStatus(s.key);
          const done = st && st !== 'PENDING';
          return (
            <button
              key={s.key}
              type="button"
              className="btn-small"
              onClick={() => { setReview(false); setStep(i); }}
              style={{ opacity: i === step && !review ? 1 : 0.85, fontWeight: i === step && !review ? 700 : 400 }}
            >
              {i + 1}. {s.label}{done ? ' ✓' : ''}
            </button>
          );
        })}
        <button type="button" className="btn-small" onClick={goReview}>Review</button>
      </div>

      {review ? (
        <ReviewScreen
          sections={sections}
          busy={busy}
          onEdit={(i) => { setReview(false); setStep(i); }}
          onComplete={handleComplete}
          onBack={() => setReview(false)}
        />
      ) : (
        <>
          {current.key === 'company' && (
            <CompanyStep
              initial={{ ...EMPTY.company, ...sectionData('company') }}
              busy={busy}
              onSave={(body) => saveSection('company', body)}
            />
          )}
          {['employees', 'machines', 'orders', 'maintenance'].includes(current.key) && (
            <RowsStep
              key={current.key}
              section={current.key}
              label={current.label}
              existing={sectionData(current.key)}
              busy={busy}
              onSave={(body) => saveSection(current.key, body)}
              onNotAvailable={() => markNotAvailable(current.key)}
            />
          )}
          {current.key === 'production' && (
            <ProductionStep
              initial={{ ...EMPTY.production, ...sectionData('production') }}
              busy={busy}
              onSave={(body) => saveSection('production', body)}
            />
          )}
          {current.key === 'thresholds' && (
            <ThresholdsStep
              initial={{ ...EMPTY.thresholds, ...sectionData('thresholds') }}
              machineTypes={[...new Set(((sectionData('machines').rows) || []).map((m) => m.machine_type).filter(Boolean))]}
              busy={busy}
              onSave={(body) => saveSection('thresholds', body)}
              onUseDefaults={async () => {
                setBusy(true); setError('');
                try { applyState(await api.useDefaultThresholds()); setNotice('Defaults applied.'); }
                catch (err) { setError(err?.message || 'Failed.'); } finally { setBusy(false); }
              }}
            />
          )}
          {current.key === 'ai_preferences' && (
            <AiPreferencesStep
              initial={{ ...EMPTY.ai_preferences, ...sectionData('ai_preferences') }}
              busy={busy}
              onSave={(body) => saveSection('ai_preferences', body)}
              onUseDefaults={async () => {
                setBusy(true); setError('');
                try { applyState(await api.useDefaultAiPreferences()); setNotice('Defaults applied.'); }
                catch (err) { setError(err?.message || 'Failed.'); } finally { setBusy(false); }
              }}
            />
          )}

          <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
            <button type="button" className="btn-secondary" onClick={back} disabled={step === 0 || busy}>← Back</button>
            <button type="button" className="btn-secondary" onClick={next} disabled={step === 7 || busy}>Skip / Next →</button>
            <button type="button" className="btn-secondary" onClick={goReview} disabled={busy}>Review all</button>
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
function CompanyStep({ initial, busy, onSave }) {
  const [form, setForm] = useState(initial);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  return (
    <section className="panel">
      <h2>Step 1 · Company / Industry Profile</h2>
      <label htmlFor="ob-name">Company / Factory name *</label>
      <input id="ob-name" value={form.name || ''} onChange={(e) => set('name', e.target.value)} style={{ width: '100%' }} />
      <label htmlFor="ob-industry" style={{ marginTop: 12, display: 'block' }}>Industry *</label>
      <select id="ob-industry" value={form.industry || ''} onChange={(e) => set('industry', e.target.value)} style={{ width: '100%' }}>
        <option value="">Select industry…</option>
        {INDUSTRIES.map((i) => <option key={i} value={i}>{i}</option>)}
      </select>
      <label htmlFor="ob-products" style={{ marginTop: 12, display: 'block' }}>Products manufactured * (comma-separated)</label>
      <input id="ob-products" value={Array.isArray(form.products) ? form.products.join(', ') : (form.products || '')}
        onChange={(e) => set('products', e.target.value)} placeholder="e.g. brackets, shafts, panels" style={{ width: '100%' }} />
      <label htmlFor="ob-count" style={{ marginTop: 12, display: 'block' }}>Employee count (recommended)</label>
      <input id="ob-count" type="number" min="0" value={form.employee_count ?? ''} onChange={(e) => set('employee_count', e.target.value)} style={{ width: 160 }} />
      <div style={{ marginTop: 16 }}>
        <button type="button" className="btn-primary" disabled={busy} onClick={() => onSave(form)}>{busy ? 'Saving…' : 'Save & Continue →'}</button>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
function ProductionStep({ initial, busy, onSave }) {
  const [form, setForm] = useState({
    processes: initial.processes || [],
    shifts: initial.shifts || [],
    capacity: initial.capacity || { value: '', unit: 'units/day' },
  });
  const addProcess = () => setForm((f) => ({ ...f, processes: [...f.processes, { name: '', sequence: f.processes.length + 1, description: '' }] }));
  const addShift = () => setForm((f) => ({ ...f, shifts: [...f.shifts, { name: 'Shift', start_time: '06:00', end_time: '14:00', break_minutes: 30, working_days: 'Mon-Fri' }] }));
  const upd = (list, i, k, v) => setForm((f) => ({ ...f, [list]: f[list].map((x, j) => (j === i ? { ...x, [k]: v } : x)) }));
  const del = (list, i) => setForm((f) => ({ ...f, [list]: f[list].filter((_, j) => j !== i) }));
  return (
    <section className="panel">
      <h2>Step 4 · Production</h2>
      <h3>Processes</h3>
      {form.processes.map((p, i) => (
        <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
          <input value={p.name} placeholder="Process name" onChange={(e) => upd('processes', i, 'name', e.target.value)} />
          <input type="number" value={p.sequence} style={{ width: 90 }} onChange={(e) => upd('processes', i, 'sequence', e.target.value)} />
          <input value={p.description} placeholder="Description" onChange={(e) => upd('processes', i, 'description', e.target.value)} style={{ flex: 1 }} />
          <button type="button" className="btn-small" onClick={() => del('processes', i)}>✕</button>
        </div>
      ))}
      <button type="button" className="btn-small" onClick={addProcess}>+ Add process</button>

      <h3 style={{ marginTop: 16 }}>Shifts</h3>
      {form.shifts.map((s, i) => (
        <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
          <input value={s.name} placeholder="Name" onChange={(e) => upd('shifts', i, 'name', e.target.value)} />
          <input value={s.start_time} placeholder="06:00" style={{ width: 90 }} onChange={(e) => upd('shifts', i, 'start_time', e.target.value)} />
          <input value={s.end_time} placeholder="14:00" style={{ width: 90 }} onChange={(e) => upd('shifts', i, 'end_time', e.target.value)} />
          <input type="number" value={s.break_minutes} placeholder="break" style={{ width: 90 }} onChange={(e) => upd('shifts', i, 'break_minutes', e.target.value)} />
          <input value={Array.isArray(s.working_days) ? s.working_days.join(',') : (s.working_days || '')} placeholder="Mon-Fri" onChange={(e) => upd('shifts', i, 'working_days', e.target.value)} />
          <button type="button" className="btn-small" onClick={() => del('shifts', i)}>✕</button>
        </div>
      ))}
      <button type="button" className="btn-small" onClick={addShift}>+ Add shift</button>

      <h3 style={{ marginTop: 16 }}>Capacity</h3>
      <div style={{ display: 'flex', gap: 8 }}>
        <input type="number" value={form.capacity.value ?? ''} placeholder="e.g. 500" style={{ width: 140 }}
          onChange={(e) => setForm((f) => ({ ...f, capacity: { ...f.capacity, value: e.target.value } }))} />
        <input value={form.capacity.unit || ''} placeholder="units/day"
          onChange={(e) => setForm((f) => ({ ...f, capacity: { ...f.capacity, unit: e.target.value } }))} />
      </div>

      <div style={{ marginTop: 16 }}>
        <button type="button" className="btn-primary" disabled={busy} onClick={() => onSave(form)}>{busy ? 'Saving…' : 'Save & Continue →'}</button>
      </div>
      <p className="muted" style={{ marginTop: 8 }}>This is configuration context only — no fake production runs are created.</p>
    </section>
  );
}

// ---------------------------------------------------------------------------
function ThresholdsStep({ initial, machineTypes, busy, onSave, onUseDefaults }) {
  const [mode, setMode] = useState(initial.mode || 'default');
  const [def, setDef] = useState({ ...DEFAULT_THRESHOLDS, ...(initial.default || {}) });
  const [byType, setByType] = useState(initial.by_type || {});
  const setTh = (k, v) => setDef((d) => ({ ...d, [k]: v }));
  const setTypeTh = (t, k, v) => setByType((bt) => ({ ...bt, [t]: { ...(bt[t] || DEFAULT_THRESHOLDS), [k]: v } }));
  return (
    <section className="panel">
      <h2>Step 7 · IoT / Machine Thresholds</h2>
      <p className="muted">Defaults: Temp {DEFAULT_THRESHOLDS.temp_max} °C · Vibration {DEFAULT_THRESHOLDS.vibration_max} mm/s · Current {DEFAULT_THRESHOLDS.current_max} A · RPM min {DEFAULT_THRESHOLDS.rpm_min}</p>
      <div style={{ display: 'flex', gap: 8, margin: '8px 0' }}>
        <button type="button" className={mode === 'default' ? 'btn-primary' : 'btn-secondary'} onClick={() => setMode('default')}>Use Defaults</button>
        <button type="button" className={mode === 'configured' ? 'btn-primary' : 'btn-secondary'} onClick={() => setMode('configured')}>Configure</button>
      </div>
      {mode === 'configured' && (
        <table className="data-table">
          <thead><tr><th>Scope</th><th>Temp max °C</th><th>Vibration max</th><th>Current max A</th><th>RPM min</th></tr></thead>
          <tbody>
            <tr>
              <td className="cell-strong">Factory default</td>
              {['temp_max', 'vibration_max', 'current_max', 'rpm_min'].map((k) => (
                <td key={k}><input type="number" value={def[k]} onChange={(e) => setTh(k, e.target.value)} /></td>
              ))}
            </tr>
            {machineTypes.map((t) => (
              <tr key={t}>
                <td className="cell-strong">{t} <span className="muted">(type)</span></td>
                {['temp_max', 'vibration_max', 'current_max', 'rpm_min'].map((k) => (
                  <td key={k}><input type="number" value={(byType[t] || DEFAULT_THRESHOLDS)[k]} onChange={(e) => setTypeTh(t, k, e.target.value)} /></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
        <button type="button" className="btn-primary" disabled={busy}
          onClick={() => onSave({ mode, default: def, by_type: byType })}>
          {busy ? 'Saving…' : 'Save Thresholds'}
        </button>
        <button type="button" className="btn-secondary" disabled={busy} onClick={onUseDefaults}>Use Defaults</button>
      </div>
      <p className="muted" style={{ marginTop: 8 }}>
        Provenance: {mode === 'default' ? 'DEFAULT' : 'FACTORY CONFIGURED'}. Applied to the existing telemetry/anomaly pipeline
        (no historical alerts are backfilled).
      </p>
    </section>
  );
}

// ---------------------------------------------------------------------------
function AiPreferencesStep({ initial, busy, onSave, onUseDefaults }) {
  const [form, setForm] = useState({
    primary_priority: initial.primary_priority || 'PRODUCTION_CONTINUITY',
    secondary_priorities: initial.secondary_priorities || [],
    recommendation_style: initial.recommendation_style || 'BALANCED',
    risk_tolerance: initial.risk_tolerance || 'BALANCED',
  });
  const toggleSecondary = (v) => setForm((f) => {
    if (v === f.primary_priority) return f;
    const has = f.secondary_priorities.includes(v);
    return { ...f, secondary_priorities: has ? f.secondary_priorities.filter((x) => x !== v) : [...f.secondary_priorities, v] };
  });
  return (
    <section className="panel">
      <h2>Step 8 · AI Preferences</h2>
      <label htmlFor="ai-primary">Primary priority</label>
      <select id="ai-primary" value={form.primary_priority} style={{ width: '100%' }}
        onChange={(e) => setForm((f) => ({
          ...f,
          primary_priority: e.target.value,
          secondary_priorities: f.secondary_priorities.filter((x) => x !== e.target.value),
        }))}>
        {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
      </select>

      <h3 style={{ marginTop: 12 }}>Secondary priorities</h3>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {PRIORITIES.filter((p) => p !== form.primary_priority).map((p) => (
          <label key={p} className="check-pill">
            <input type="checkbox" checked={form.secondary_priorities.includes(p)} onChange={() => toggleSecondary(p)} /> {p}
          </label>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 16, marginTop: 16, flexWrap: 'wrap' }}>
        <div>
          <label htmlFor="ai-style">Recommendation style</label>
          <select id="ai-style" value={form.recommendation_style} onChange={(e) => setForm((f) => ({ ...f, recommendation_style: e.target.value }))}>
            {STYLES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="ai-risk">Risk tolerance</label>
          <select id="ai-risk" value={form.risk_tolerance} onChange={(e) => setForm((f) => ({ ...f, risk_tolerance: e.target.value }))}>
            {RISKS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>

      <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
        <button type="button" className="btn-primary" disabled={busy} onClick={() => onSave(form)}>{busy ? 'Saving…' : 'Save Preferences'}</button>
        <button type="button" className="btn-secondary" disabled={busy} onClick={onUseDefaults}>Use Defaults</button>
      </div>
      <p className="muted" style={{ marginTop: 8 }}>Stored in the factory onboarding context and exposed to the existing AI assistant context.</p>
    </section>
  );
}

// ---------------------------------------------------------------------------
function RowsStep({ section, label, existing, busy, onSave, onNotAvailable }) {
  const spec = CSV_SPECS[section];
  const [mode, setMode] = useState('csv'); // csv | manual
  const [text, setText] = useState('');
  const [fileError, setFileError] = useState('');
  const [preview, setPreview] = useState(null); // {rows, validation}
  const [manualRows, setManualRows] = useState(() => (existing?.rows?.length ? existing.rows : []));

  const parsed = useMemo(() => parseCsv(text), [text]);
  const validation = useMemo(() => (parsed.rows.length ? validateRows(section, parsed.rows) : null), [parsed, section]);

  const onFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const content = await file.text();
      setText(content);
      setFileError('');
      setPreview(validateRows(section, parseCsv(content).rows));
    } catch (err) {
      setFileError(String(err?.message || err));
    }
  };

  const buildPreview = () => {
    if (!validation) return;
    setPreview(validation);
  };

  const addManual = () => {
    const row = {};
    spec.headers.forEach((h) => { row[h] = ''; });
    setManualRows((r) => [...r, row]);
  };
  const updManual = (i, k, v) => setManualRows((r) => r.map((row, j) => (j === i ? { ...row, [k]: v } : row)));
  const delManual = (i) => setManualRows((r) => r.filter((_, j) => j !== i));

  const submitManual = () => {
    const v = validateRows(section, manualRows);
    if (v.errors.length) { setPreview(v); return; }
    onSave({ mode: 'available', rows: v.ok });
  };

  const submitCsv = () => {
    if (!validation || validation.errors.length) { setPreview(validation || { errors: [{ row: 0, message: 'no data' }], ok: [] }); return; }
    onSave({ mode: 'available', rows: validation.ok });
  };

  return (
    <section className="panel">
      <h2>{label}</h2>
      <p className="muted">
        {section === 'employees' && 'CSV: employee_id,name,role,department,skills,certifications,shift,experience_years'}
        {section === 'machines' && 'CSV: machine_id,machine_name,type,location,department,criticality,status — equivalent IDs (M-001/M001) resolve consistently'}
        {section === 'orders' && 'CSV: order_id,customer,product,quantity,priority,deadline'}
        {section === 'maintenance' && 'CSV: maintenance_id,machine_id,date,issue,action,resolution,technician,downtime_hours,status'}
      </p>

      <div style={{ display: 'flex', gap: 8, margin: '8px 0' }}>
        <button type="button" className={mode === 'csv' ? 'btn-primary' : 'btn-secondary'} onClick={() => setMode('csv')}>Upload CSV / Paste</button>
        <button type="button" className={mode === 'manual' ? 'btn-primary' : 'btn-secondary'} onClick={() => setMode('manual')}>Manual entry</button>
        <button type="button" className="btn-secondary" disabled={busy} onClick={onNotAvailable}>Not Available</button>
      </div>

      {mode === 'csv' && (
        <>
          <input type="file" accept=".csv,text/csv" onChange={onFile} />
          {fileError && <p className="muted" role="alert">{fileError}</p>}
          <textarea value={text} onChange={(e) => { setText(e.target.value); setPreview(null); }} rows={6}
            placeholder={`Paste CSV here, e.g.\n${spec.headers.join(',')}`} style={{ width: '100%', marginTop: 8 }} />
          <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
            <button type="button" className="btn-secondary" onClick={buildPreview} disabled={!text.trim()}>Preview</button>
            <button type="button" className="btn-primary" disabled={busy || !text.trim()} onClick={submitCsv}>{busy ? 'Importing…' : 'Confirm & Import'}</button>
          </div>
        </>
      )}

      {mode === 'manual' && (
        <>
          <table className="data-table" style={{ marginTop: 8 }}>
            <thead><tr>{spec.headers.map((h) => <th key={h}>{h}</th>)}<th /></tr></thead>
            <tbody>
              {manualRows.map((row, i) => (
                <tr key={i}>
                  {spec.headers.map((h) => (
                    <td key={h}><input value={row[h] ?? ''} onChange={(e) => updManual(i, h, e.target.value)} /></td>
                  ))}
                  <td><button type="button" className="btn-small" onClick={() => delManual(i)}>✕</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
            <button type="button" className="btn-small" onClick={addManual}>+ Add row</button>
            <button type="button" className="btn-primary" disabled={busy || !manualRows.length} onClick={submitManual}>{busy ? 'Saving…' : 'Save rows'}</button>
          </div>
        </>
      )}

      {preview && (
        <div style={{ marginTop: 16 }}>
          <h3>Preview ({preview.ok?.length || 0} valid{preview.errors?.length ? `, ${preview.errors.length} with errors` : ''})</h3>
          {preview.errors?.length > 0 && (
            <div className="alert-banner" role="alert">
              {preview.errors.map((e, i) => <div key={i}>Row {e.row}: {e.message}</div>)}
            </div>
          )}
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead><tr>{spec.headers.map((h) => <th key={h}>{h}</th>)}</tr></thead>
              <tbody>
                {(preview.ok || []).slice(0, 50).map((row, i) => (
                  <tr key={i}>{spec.headers.map((h) => <td key={h}>{String(row[h] ?? '')}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {existing?.count > 0 && (
        <p className="muted" style={{ marginTop: 12 }} role="status">
          Already imported: {existing.count} row(s){existing.skipped ? `, ${existing.skipped} skipped as duplicates` : ''}.
        </p>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
function Row({ label, value }) {
  return (
    <tr><td className="cell-strong">{label}</td><td>{value}</td></tr>
  );
}

function ReviewScreen({ sections, busy, onEdit, onComplete, onBack }) {
  const d = (k) => sections?.[k]?.data || {};
  const st = (k) => sections?.[k]?.status || 'PENDING';
  const company = d('company');
  const production = d('production');
  const thresholds = d('thresholds');
  const ai = d('ai_preferences');
  const required = ['company', 'machines', 'thresholds', 'ai_preferences'];
  const missing = required.filter((k) => st(k) === 'PENDING');
  return (
    <section className="panel">
      <h2>Review &amp; Complete Setup</h2>
      {missing.length > 0 && (
        <div className="alert-banner" role="alert">
          Finish required section(s) first: {missing.map((m) => STEPS.find((s) => s.key === m)?.label || m).join(', ')}
        </div>
      )}
      <table className="data-table">
        <tbody>
          <Row label="Company" value={<>{company.name || '—'} <button type="button" className="btn-small" onClick={() => onEdit(0)}>edit</button></>} />
          <Row label="Industry" value={company.industry || '—'} />
          <Row label="Products" value={(company.products || []).join?.(', ') || company.products || '—'} />
          <Row label="Employees" value={<>{countLabel(st('employees'), d('employees').count)} <button type="button" className="btn-small" onClick={() => onEdit(1)}>edit</button></>} />
          <Row label="Machines" value={<>{countLabel(st('machines'), d('machines').count)} <button type="button" className="btn-small" onClick={() => onEdit(2)}>edit</button></>} />
          <Row label="Production" value={production.processes?.length ? `${production.processes.length} processes, ${production.shifts?.length || 0} shifts` : '—'} />
          <Row label="Orders" value={<>{countLabel(st('orders'), d('orders').count)} <button type="button" className="btn-small" onClick={() => onEdit(4)}>edit</button></>} />
          <Row label="Maintenance" value={countLabel(st('maintenance'), d('maintenance').count)} />
          <Row label="IoT Thresholds" value={st('thresholds') === 'DEFAULT' ? 'DEFAULT' : `FACTORY CONFIGURED (temp ≤ ${thresholds.default?.temp_max ?? 85}, vib ≤ ${thresholds.default?.vibration_max ?? 5})`} />
          <Row label="AI Preferences" value={`${ai.primary_priority || 'PRODUCTION_CONTINUITY'} · ${ai.recommendation_style || 'BALANCED'} · ${ai.risk_tolerance || 'BALANCED'}`} />
        </tbody>
      </table>
      <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
        <button type="button" className="btn-secondary" onClick={onBack}>← Back to steps</button>
        <button type="button" className="btn-primary" disabled={busy || missing.length > 0} onClick={onComplete}>
          {busy ? 'Completing…' : 'Complete Setup →'}
        </button>
      </div>
    </section>
  );
}

function countLabel(status, count) {
  if (status === 'NOT_AVAILABLE') return 'Not Available';
  if (status === 'DEFAULT') return 'Default';
  return `${count || 0} imported`;
}
