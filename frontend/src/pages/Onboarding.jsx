import { useState } from 'react';
import { api } from '../services/api';
import StatusBadge from '../components/StatusBadge';

const MACHINE_OPTIONS = ['CNC Mill', 'CNC Lathe / Turning', 'Hydraulic Press', 'Surface Grinder', 'Welding Station', 'Assembly Robot', 'Laser Cutter', 'Injection Molding', 'Drill Press', 'Bandsaw'];
const PROBLEM_OPTIONS = ['Order delays', 'Machine breakdowns', 'Quality issues', 'Overtime overload', 'Spare-parts shortage', 'Skilled-worker shortage'];

const EMPTY = {
  industry: 'CNC / Mechanical',
  products: '',
  machine_types: ['CNC Mill', 'CNC Lathe / Turning'],
  machine_types_other: '',
  shifts_count: '2',
  workforce: '',
  skills_text: '',
  main_problems: ['Order delays', 'Machine breakdowns'],
  has_files: 'no',
};

function toggle(list, v) {
  return list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
}

export default function Onboarding({ onDone, onSkipToImport }) {
  const [answers, setAnswers] = useState(EMPTY);
  const [step, setStep] = useState('questions'); // questions | generating | review
  const [draft, setDraft] = useState(null);
  const [source, setSource] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [seedInfo, setSeedInfo] = useState(null);

  const set = (k, v) => setAnswers((a) => ({ ...a, [k]: v }));

  const handleGenerate = async () => {
    setStep('generating');
    setError('');
    setBusy(true);
    try {
      const res = await api.generateProfile(answers);
      setDraft(res.profile);
      setSource(res.source || res.profile?._source || 'preset');
      setStep('review');
    } catch (err) {
      setError(err.message || 'Profile generation failed');
      setStep('questions');
    } finally {
      setBusy(false);
    }
  };

  const handleSkipPreset = async () => {
    setError('');
    setBusy(true);
    try {
      const preset = await api.presetProfile();
      const profile = preset.profile || preset;
      await api.saveProfile(profile);
      const approved = await api.approveProfile();
      setSeedInfo(approved.seed || null);
      onDone();
    } catch (err) {
      setError(err.message || 'Skip with preset failed. Is the backend running and migration applied?');
    } finally {
      setBusy(false);
    }
  };

  const updateMachine = (i, field, value) => {
    setDraft((d) => ({
      ...d,
      machines: d.machines.map((m, j) => (j === i ? { ...m, [field]: value } : m)),
    }));
  };

  const updateThreshold = (type, field, value) => {
    setDraft((d) => ({
      ...d,
      thresholds: { ...d.thresholds, [type]: { ...d.thresholds[type], [field]: Number(value) } },
    }));
  };

  const handleApprove = async () => {
    setError('');
    setBusy(true);
    try {
      await api.saveProfile(draft);
      const approved = await api.approveProfile();
      setSeedInfo(approved.seed || null);
      onDone();
    } catch (err) {
      setError(err.message || 'Approve failed');
    } finally {
      setBusy(false);
    }
  };

  if (step === 'generating') {
    return (
      <div className="page">
        <div className="page-head"><div><h2>Setting up your factory…</h2><p className="page-desc">AI is drafting machines, sensors, alert limits and task steps from your answers.</p></div></div>
        <section className="panel"><p className="muted">Generating profile… (falls back to the CNC preset when AI is unavailable)</p></section>
      </div>
    );
  }

  if (step === 'review' && draft) {
    const thresholds = draft.thresholds || {};
    return (
      <div className="page">
        <div className="page-head">
          <div>
            <h2>Review your factory setup</h2>
            <p className="page-desc">Edit anything before approving. Every AI proposal is applied only after you approve.</p>
          </div>
          <StatusBadge tone={source === 'ai' ? 'info' : 'warn'}>{source === 'ai' ? 'AI-generated draft' : 'Preset (AI unavailable)'}</StatusBadge>
        </div>
        {error && <div className="alert-banner" role="alert">{error}</div>}

        <section className="panel">
          <h2>Machines ({(draft.machines || []).length})</h2>
          <table className="data-table">
            <thead><tr><th>Code</th><th>Name</th><th>Type</th><th>Location</th><th>Sensors</th></tr></thead>
            <tbody>
              {(draft.machines || []).map((m, i) => (
                <tr key={m.code || i}>
                  <td className="cell-mono">{m.code}</td>
                  <td><input value={m.name || ''} onChange={(e) => updateMachine(i, 'name', e.target.value)} /></td>
                  <td><input value={m.machine_type || ''} onChange={(e) => updateMachine(i, 'machine_type', e.target.value)} /></td>
                  <td><input value={m.location || ''} onChange={(e) => updateMachine(i, 'location', e.target.value)} /></td>
                  <td className="muted">{(m.sensors || []).join(', ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="panel">
          <h2>Alert limits (per machine type)</h2>
          <table className="data-table">
            <thead><tr><th>Type</th><th>Temp max °C</th><th>Vibration max</th><th>Current max A</th><th>RPM min</th></tr></thead>
            <tbody>
              {Object.entries(thresholds).filter(([k]) => !k.startsWith('_')).map(([t, v]) => (
                <tr key={t}>
                  <td className="cell-strong">{t}</td>
                  <td><input type="number" value={v.temp_max} onChange={(e) => updateThreshold(t, 'temp_max', e.target.value)} /></td>
                  <td><input type="number" step="0.1" value={v.vibration_max} onChange={(e) => updateThreshold(t, 'vibration_max', e.target.value)} /></td>
                  <td><input type="number" step="0.1" value={v.current_max} onChange={(e) => updateThreshold(t, 'current_max', e.target.value)} /></td>
                  <td><input type="number" value={v.rpm_min} onChange={(e) => updateThreshold(t, 'rpm_min', e.target.value)} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="panel">
          <h2>Task templates ({(draft.task_templates || []).length}) · Skills · Shifts</h2>
          <ul className="task-list">
            {(draft.task_templates || []).slice(0, 9).map((t, i) => (
              <li key={i} className="task-row"><div className="task-main"><span className="cell-strong">{t.name}</span><span className="task-meta">{t.required_skill || ''} · {t.machine_type || ''}</span></div></li>
            ))}
          </ul>
          <p className="muted" style={{ marginTop: 8 }}>Skills: {(draft.skills || []).join(', ') || '—'}</p>
          <p className="muted">Shifts: {(draft.shifts || []).join(', ') || '—'}</p>
        </section>

        <div style={{ display: 'flex', gap: 8 }}>
          <button type="button" className="btn-secondary" onClick={() => setStep('questions')} disabled={busy}>← Back</button>
          <button type="button" className="btn-primary" onClick={handleApprove} disabled={busy}>{busy ? 'Approving…' : 'Approve & continue →'}</button>
          {onSkipToImport && <button type="button" className="btn-small" onClick={onSkipToImport}>Continue without approving</button>}
        </div>
        {seedInfo && <p className="muted" role="status">Seeded machines: {seedInfo.created} created · {seedInfo.skipped} skipped (idempotent).</p>}
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>Welcome to IndAI — factory setup</h2>
          <p className="page-desc">Answer 6 quick questions. AI drafts your machines, sensors, alert limits and task steps for review.</p>
        </div>
      </div>
      {error && <div className="alert-banner" role="alert">{error}</div>}

      <section className="panel">
        <h2>1 · Industry — what do you make?</h2>
        <input value={answers.products} onChange={(e) => set('products', e.target.value)} placeholder="e.g. milled brackets, shafts, sheet-metal panels" style={{ width: '100%' }} />
        <p className="muted" style={{ marginTop: 8 }}>Industry preset: <b>{answers.industry}</b> (CNC / mechanical demo default)</p>
      </section>

      <section className="panel">
        <h2>2 · Which machines do you have?</h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {MACHINE_OPTIONS.map((m) => (
            <label key={m} className="check-pill"><input type="checkbox" checked={answers.machine_types.includes(m)} onChange={() => set('machine_types', toggle(answers.machine_types, m))} /> {m}</label>
          ))}
        </div>
        <input value={answers.machine_types_other} onChange={(e) => set('machine_types_other', e.target.value)} placeholder="Other machines (free text)" style={{ width: '100%', marginTop: 8 }} />
      </section>

      <section className="panel">
        <h2>3 · How many shifts?</h2>
        <select value={answers.shifts_count} onChange={(e) => set('shifts_count', e.target.value)}>
          <option value="1">1 shift</option>
          <option value="2">2 shifts</option>
          <option value="3">3 shifts</option>
        </select>
      </section>

      <section className="panel">
        <h2>4 · Workforce size & key skills</h2>
        <input value={answers.workforce} onChange={(e) => set('workforce', e.target.value)} placeholder="e.g. 12 people across 2 shifts" style={{ width: '100%' }} />
        <input value={answers.skills_text} onChange={(e) => set('skills_text', e.target.value)} placeholder="Key skills, e.g. CNC operation, welding, QC" style={{ width: '100%', marginTop: 8 }} />
      </section>

      <section className="panel">
        <h2>5 · Main problems</h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {PROBLEM_OPTIONS.map((p) => (
            <label key={p} className="check-pill"><input type="checkbox" checked={answers.main_problems.includes(p)} onChange={() => set('main_problems', toggle(answers.main_problems, p))} /> {p}</label>
          ))}
        </div>
      </section>

      <section className="panel">
        <h2>6 · Do you already have Excel / CSV files?</h2>
        <select value={answers.has_files} onChange={(e) => set('has_files', e.target.value)}>
          <option value="no">No — start empty</option>
          <option value="yes">Yes — I will upload them after setup</option>
        </select>
      </section>

      <div style={{ display: 'flex', gap: 8 }}>
        <button type="button" className="btn-primary" onClick={handleGenerate} disabled={busy}>{busy ? 'Generating…' : 'Generate my factory setup →'}</button>
        <button type="button" className="btn-secondary" onClick={handleSkipPreset} disabled={busy}>Skip — use CNC preset</button>
      </div>
    </div>
  );
}
