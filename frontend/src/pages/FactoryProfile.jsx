import { useCallback, useEffect, useState } from 'react';
import { api } from '../services/api';
import RefreshBar from '../components/RefreshBar';
import useAutoRefresh from '../hooks/useAutoRefresh';
import StatCard from '../components/StatCard';
import StatusBadge from '../components/StatusBadge';

export default function FactoryProfile() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    setError('');
    try {
      const res = await api.profile();
      setData(res);
    } catch (err) {
      setError(err.message || 'Failed to load factory profile');
    } finally {
      if (!quiet) setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const profile = data?.profile || {};
  const source = data?.source || profile._source || 'preset';

  const handleSave = async () => {
    setSaving(true);
    setSaveMsg('');
    setError('');
    try {
      const res = await api.saveProfile(profile);
      setData(res);
      setSaveMsg('Draft saved. Re-approve from onboarding only if machines changed.');
    } catch (err) {
      setError(err.message || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  // One-click repair: replace only the alert limits with the preset
  // per-type defaults (machines, templates, skills untouched), so an
  // already-approved profile picks up threshold fixes without re-onboarding.
  const handleResetThresholds = async () => {
    setSaving(true);
    setSaveMsg('');
    setError('');
    try {
      const preset = await api.presetProfile();
      const presetThresholds = (preset.profile || preset).thresholds;
      if (!presetThresholds) throw new Error('Preset has no thresholds');
      const res = await api.saveProfile({ ...profile, thresholds: presetThresholds });
      setData(res);
      setSaveMsg('Alert limits reset to preset defaults. Detection uses them immediately (profile stays approved).');
    } catch (err) {
      setError(err.message || 'Reset failed');
    } finally {
      setSaving(false);
    }
  };

  const refresher = useAutoRefresh(load);

  return (
    <div className="page">
      <RefreshBar auto={refresher.auto} onAuto={refresher.setAuto} onReload={refresher.refreshNow} refreshing={refresher.refreshing} lastRefresh={refresher.lastRefresh} />
      <div className="page-head">
        <div>
          <h2>Factory Profile</h2>
          <p className="page-desc">Approved setup: machines, sensors, alert limits, task steps, skills and shifts.</p>
        </div>
        {data && <StatusBadge tone={data.status === 'APPROVED' ? 'ok' : 'warn'}>{data.status || '—'} · {source === 'ai' ? 'AI' : 'Preset'}</StatusBadge>}
      </div>

      <section className="stat-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        <StatCard label="Industry" value={profile.industry || '—'} sub={data?.industry || ''} loading={loading} />
        <StatCard label="Machines" value={(profile.machines || []).length} sub="configured" loading={loading} />
        <StatCard label="Task templates" value={(profile.task_templates || []).length} sub="steps" loading={loading} />
        <StatCard label="Skills" value={(profile.skills || []).length} sub={(profile.shifts || []).join(' · ') || 'shifts'} loading={loading} />
      </section>

      {error && <div className="alert-banner" role="alert">{error} <button type="button" className="btn-small" onClick={load}>Retry</button></div>}
      {saveMsg && <div className="panel" role="status"><p className="muted">{saveMsg}</p></div>}

      {!loading && !error && data && (
        <>
          <section className="panel">
            <h2>Machines</h2>
            <table className="data-table">
              <thead><tr><th>Code</th><th>Name</th><th>Type</th><th>Location</th><th>Sensors</th></tr></thead>
              <tbody>
                {(profile.machines || []).map((m) => (
                  <tr key={m.code}><td className="cell-mono">{m.code}</td><td className="cell-strong">{m.name}</td><td>{m.machine_type}</td><td className="muted">{m.location}</td><td className="muted">{(m.sensors || []).join(', ')}</td></tr>
                ))}
              </tbody>
            </table>
          </section>
          <section className="panel">
            <h2>Alert limits</h2>
            <table className="data-table">
              <thead><tr><th>Type</th><th>Temp max</th><th>Vib max</th><th>Curr max</th><th>RPM min</th></tr></thead>
              <tbody>
                {Object.entries(profile.thresholds || {}).filter(([k]) => !k.startsWith('_')).map(([t, v]) => (
                  <tr key={t}><td className="cell-strong">{t}</td><td className="cell-mono">{v.temp_max}</td><td className="cell-mono">{v.vibration_max}</td><td className="cell-mono">{v.current_max}</td><td className="cell-mono">{v.rpm_min}</td></tr>
                ))}
              </tbody>
            </table>
            <p className="muted" style={{ marginTop: 8 }}>Live detection uses these limits when approved (deterministic); otherwise built-in defaults apply.</p>
            <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
              <button type="button" className="btn-secondary" onClick={handleResetThresholds} disabled={saving}>
                {saving ? 'Resetting…' : 'Reset thresholds to preset defaults'}
              </button>
            </div>
          </section>
          <section className="panel">
            <h2>Terminology · Skills · Shifts · Problems</h2>
            <p className="muted">Terms: {profile.terminology?.machine || 'machine'} / {profile.terminology?.order || 'order'} / {profile.terminology?.task || 'task'}</p>
            <p className="muted">Skills: {(profile.skills || []).join(', ') || '—'}</p>
            <p className="muted">Shifts: {(profile.shifts || []).join(', ') || '—'} · Problems: {(profile.main_problems || []).join(', ') || '—'}</p>
            <div style={{ marginTop: 12 }}>
              <button type="button" className="btn-secondary" onClick={handleSave} disabled={saving}>{saving ? 'Saving…' : 'Save (draft)'}</button>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
