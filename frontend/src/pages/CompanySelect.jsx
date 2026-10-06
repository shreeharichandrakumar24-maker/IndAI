import { useCallback, useEffect, useState } from 'react';
import { api } from '../services/api';
import { setSelectedFactory } from '../services/factory';
import StatusBadge from '../components/StatusBadge';

// Part 1 — lightweight "who are you" entry page. NOT authentication: it just
// picks which company/factory the demo session works in. The choice is stored
// in localStorage so a refresh (or "switch company") keeps it.
export default function CompanySelect({ onEnter }) {
  const [factories, setFactories] = useState([]);
  const [industries, setIndustries] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [newIndustry, setNewIndustry] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.factories();
      const list = res.factories || [];
      setFactories(list);
      setIndustries(res.industries || []);
      setSelectedId((cur) => cur || list[0]?.id || null);
    } catch (err) {
      setError(err.message || 'Could not load companies. Is the backend running and migration 008 applied?');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const selected = factories.find((f) => f.id === selectedId) || null;

  const handleContinue = () => {
    if (!selected) return;
    setSelectedFactory(selected);
    onEnter(selected);
  };

  const handleCreate = async (e) => {
    e?.preventDefault?.();
    const name = newName.trim();
    if (!name) { setError('Enter a company / factory name.'); return; }
    setBusy(true);
    setError('');
    try {
      const created = await api.createFactory({ name, industry: newIndustry || null });
      setSelectedFactory(created);
      onEnter(created);
    } catch (err) {
      setError(err.message || 'Could not create the company.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="shell">
      <div className="main">
        <div className="page" style={{ maxWidth: 1080, margin: '0 auto' }}>
          <div className="page-head" style={{ textAlign: 'center', display: 'block' }}>
            <h1 style={{ marginBottom: 4 }}>Welcome to IndAI</h1>
            <p className="page-desc">Choose a company / factory to continue, or create a new one.</p>
          </div>

          {error && (
            <div className="alert-banner" role="alert">
              {error} <button type="button" className="btn-small" onClick={load}>Retry</button>
            </div>
          )}

          {loading ? (
            <p className="muted">Loading factories…</p>
          ) : (
            <>
              <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}>
                {factories.map((f) => {
                  const active = f.id === selectedId;
                  return (
                    <button
                      key={f.id}
                      type="button"
                      className="panel"
                      onClick={() => setSelectedId(f.id)}
                      style={{
                        textAlign: 'left', cursor: 'pointer', display: 'block', width: '100%',
                        borderColor: active ? 'var(--accent, #4f8cff)' : undefined,
                        outline: active ? '2px solid var(--accent, #4f8cff)' : 'none',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                        <h2 style={{ margin: 0, fontSize: 18 }}>{f.name}</h2>
                        <StatusBadge tone={f.setup_complete ? 'ok' : 'warn'}>
                          {f.setup_complete ? 'SETUP COMPLETE' : 'SETUP INCOMPLETE'}
                        </StatusBadge>
                      </div>
                      <p className="muted" style={{ marginTop: 6 }}>{f.industry || 'Industry not set'}{f.is_default ? ' · legacy company' : ''}</p>
                      <p className="muted" style={{ marginTop: 6 }}>
                        {f.counts?.employees ?? 0} employees · {f.counts?.machines ?? 0} machines ·{' '}
                        {f.counts?.orders ?? 0} orders · {f.counts?.maintenance ?? 0} maintenance
                      </p>
                      <p className="muted">Onboarding: {f.onboarding_status || 'DRAFT'} · step {f.current_step || 1}/8</p>
                    </button>
                  );
                })}
              </div>

              <div style={{ display: 'flex', gap: 12, marginTop: 20, justifyContent: 'center', flexWrap: 'wrap' }}>
                <button type="button" className="btn-primary" onClick={handleContinue} disabled={!selected}>
                  Continue{selected ? ` as ${selected.name}` : ''} →
                </button>
                <button type="button" className="btn-secondary" onClick={() => setCreating((c) => !c)}>
                  {creating ? 'Cancel' : '+ Create New Company / Factory'}
                </button>
              </div>

              {creating && (
                <section className="panel" style={{ marginTop: 20, maxWidth: 560, marginLeft: 'auto', marginRight: 'auto' }}>
                  <h2>New company / factory</h2>
                  <form onSubmit={handleCreate}>
                    <label htmlFor="cf-name">Company / Factory name *</label>
                    <input
                      id="cf-name"
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      placeholder="e.g. Northgate Precision Works"
                      style={{ width: '100%' }}
                      autoFocus
                    />
                    <label htmlFor="cf-industry" style={{ marginTop: 12, display: 'block' }}>Industry (optional)</label>
                    <select id="cf-industry" value={newIndustry} onChange={(e) => setNewIndustry(e.target.value)} style={{ width: '100%' }}>
                      <option value="">Select industry…</option>
                      {industries.map((i) => <option key={i} value={i}>{i}</option>)}
                    </select>
                    <p className="muted" style={{ marginTop: 10 }}>
                      It starts as DRAFT with incomplete onboarding — you'll go straight to Step 1.
                    </p>
                    <button type="submit" className="btn-primary" disabled={busy} style={{ marginTop: 8 }}>
                      {busy ? 'Creating…' : 'Create & start onboarding →'}
                    </button>
                  </form>
                </section>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
