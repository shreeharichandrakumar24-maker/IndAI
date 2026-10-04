import { useCallback, useEffect, useState } from 'react';
import { api } from '../services/api';
import RefreshBar from '../components/RefreshBar';
import useAutoRefresh from '../hooks/useAutoRefresh';
import StatCard from '../components/StatCard';
import StatusBadge from '../components/StatusBadge';
import ProgressTracker from '../components/plans/ProgressTracker';
import LivePlan from '../components/plans/LivePlan';

function toneForPlan(s) {
  if (s === 'DISPATCHED' || s === 'DONE') return 'ok';
  if (s === 'APPROVED') return 'info';
  return 'warn';
}

function toneForSource(source) {
  return source === 'ai' ? 'info' : 'warn';
}

const EMPTY_ITEM = { task_name: '', required_skill: '', machine_type: '', priority: 'NORMAL' };

// Manager console for work plans (Phase 7 + F6): draft items -> approve
// (creates tasks) -> AI-suggest pairings -> Apply per item -> dispatch.
// Progress tracker + Live plan tabs join live task state on every read.
export default function Plans({ onNavigate }) {
  const [tab, setTab] = useState('plans');
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);
  const [assignments, setAssignments] = useState([]);
  const [suggestions, setSuggestions] = useState(null);
  const [busy, setBusy] = useState('');
  const [actionMsg, setActionMsg] = useState(null);

  // progress tracker state
  const [trackPlanId, setTrackPlanId] = useState('');
  const [progress, setProgress] = useState(null);
  const [progressLoading, setProgressLoading] = useState(false);
  const [progressError, setProgressError] = useState('');
  const [workerFilter, setWorkerFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [overdueOnly, setOverdueOnly] = useState(false);

  // live plan state
  const [live, setLive] = useState(null);
  const [liveLoading, setLiveLoading] = useState(false);
  const [liveError, setLiveError] = useState('');
  const [attaching, setAttaching] = useState('');

  // create form
  const [title, setTitle] = useState('');
  const [items, setItems] = useState([{ ...EMPTY_ITEM }]);

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    setError('');
    try {
      const data = await api.plans();
      setPlans(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message || 'Failed to load plans');
    } finally {
      if (!quiet) setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openPlan = async (p) => {
    setSelected(p);
    setSuggestions(null);
    setActionMsg(null);
    try {
      const a = await api.planAssignments(p.id);
      setAssignments(Array.isArray(a) ? a : []);
    } catch (err) {
      setError(err.message || 'Failed to load assignments');
    }
  };

  const refreshSelected = async (planId) => {
    const [p, a] = await Promise.all([api.plan(planId), api.planAssignments(planId)]);
    setSelected(p);
    setAssignments(Array.isArray(a) ? a : []);
    await load();
  };

  const run = async (key, fn, okMsg) => {
    setBusy(key);
    setError('');
    setActionMsg(null);
    try {
      const res = await fn();
      if (okMsg) setActionMsg(typeof okMsg === 'function' ? okMsg(res) : okMsg);
      if (selected) await refreshSelected(selected.id);
      else await load();
      return res;
    } catch (err) {
      setError(err.message || 'Action failed');
      return null;
    } finally {
      setBusy('');
    }
  };

  const handleCreate = () => run('create', async () => {
    const clean = items.map((i) => ({
      task_name: i.task_name.trim(),
      required_skill: i.required_skill.trim() || null,
      machine_type: i.machine_type.trim() || null,
      priority: i.priority,
    })).filter((i) => i.task_name);
    if (!title.trim()) throw new Error('Plan title is required');
    if (clean.length === 0) throw new Error('Add at least one item with a task name');
    return api.createPlan({ title: title.trim(), items: clean });
  }, 'Plan drafted.').then((p) => {
    if (p) { setTitle(''); setItems([{ ...EMPTY_ITEM }]); openPlan(p); }
  });

  const handleSuggest = () => run('suggest', () => api.suggestAssignments(selected.id), (res) => {
    setSuggestions(res);
    const n = (res.suggestions || []).filter((s) => s.status === 'SUGGESTED').length;
    return `Suggestions ready (${res.source === 'ai' ? 'AI-ranked' : 'deterministic fallback'}): ${n} suggested.`;
  });

  const handleApply = (s) => run(`apply-${s.assignment_id}`, () =>
    api.pairAssignment(s.assignment_id, { employee_id: s.employee_id, machine_id: s.machine_id }),
    'Pairing applied to task + assignment.');

  const drafts = plans.filter((p) => p.status === 'DRAFT').length;
  const sugById = Object.fromEntries((suggestions?.suggestions || []).map((s) => [s.assignment_id, s]));

  const refresher = useAutoRefresh(load);

  const loadProgress = useCallback(async (quiet = false) => {
    if (!trackPlanId) return;
    if (!quiet) setProgressLoading(true);
    setProgressError('');
    try {
      setProgress(await api.planProgress(trackPlanId));
    } catch (err) {
      setProgressError(err.message || 'Failed to load progress');
    } finally {
      if (!quiet) setProgressLoading(false);
    }
  }, [trackPlanId]);

  const loadLive = useCallback(async (quiet = false) => {
    if (!quiet) setLiveLoading(true);
    setLiveError('');
    try {
      setLive(await api.livePlans());
    } catch (err) {
      setLiveError(err.message || 'Failed to load live plan');
    } finally {
      if (!quiet) setLiveLoading(false);
    }
  }, []);

  useAutoRefresh(loadProgress, { paused: tab !== 'progress' || !trackPlanId });
  useAutoRefresh(loadLive, { paused: tab !== 'live' });

  useEffect(() => {
    if (trackPlanId) loadProgress();
  }, [trackPlanId, loadProgress]);

  useEffect(() => {
    if (tab === 'live') loadLive();
  }, [tab, loadLive]);

  // Default the tracker to the newest non-draft plan.
  useEffect(() => {
    if (!trackPlanId) {
      const cand = plans.find((p) => p.status !== 'DRAFT');
      if (cand) setTrackPlanId(cand.id);
    }
  }, [plans, trackPlanId]);

  const handleAttach = async (planId, taskId) => {
    setAttaching(taskId);
    setError('');
    try {
      await api.attachPlanItem(planId, taskId);
      setActionMsg('Task added to plan.');
      await loadLive(true);
      if (trackPlanId === planId) await loadProgress(true);
    } catch (err) {
      setError(err.message || 'Attach failed');
    } finally {
      setAttaching('');
    }
  };

  return (
    <div className="page">
      <RefreshBar auto={refresher.auto} onAuto={refresher.setAuto} onReload={refresher.refreshNow} refreshing={refresher.refreshing} lastRefresh={refresher.lastRefresh} />
      <div className="page-head">
        <div>
          <h2>Work plans</h2>
          <p className="page-desc">Draft → approve (creates tasks) → AI-suggest pairings → apply → dispatch to workers.</p>
        </div>
        {suggestions && <StatusBadge tone={toneForSource(suggestions.source)}>{suggestions.source === 'ai' ? 'AI-ranked' : 'Deterministic fallback'}</StatusBadge>}
      </div>

      <div className="split-tabs" role="tablist" aria-label="Work plans views">
        {[['plans', 'Plans'], ['progress', 'Progress tracker'], ['live', 'Live plan']].map(([id, label]) => (
          <button key={id} type="button" role="tab" aria-selected={tab === id}
            className={`split-tab${tab === id ? ' active' : ''}`} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'progress' && (
        <ProgressTracker data={progress} loading={progressLoading} error={progressError}
          plans={plans} planId={trackPlanId} onPlan={setTrackPlanId}
          workerFilter={workerFilter} onWorkerFilter={setWorkerFilter}
          statusFilter={statusFilter} onStatusFilter={setStatusFilter}
          overdueOnly={overdueOnly} onOverdueOnly={setOverdueOnly}
          onNavigate={onNavigate} />
      )}

      {tab === 'live' && (
        <LivePlan data={live} loading={liveLoading} error={liveError}
          plans={plans} onAttach={handleAttach} attaching={attaching} />
      )}

      {tab === 'plans' && (
      <>
      <section className="stat-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
        <StatCard label="Plans" value={plans.length} sub={`${drafts} drafts`} loading={loading} />
        <StatCard label="Items open" value={selected ? assignments.length : '—'} sub={selected ? selected.title : 'open a plan'} loading={loading} />
        <StatCard label="Suggestions" value={suggestions ? suggestions.suggestions.length : '—'} sub={suggestions ? suggestions.source : 'not requested'} loading={false} />
      </section>

      {error && <div className="alert-banner" role="alert">{error}</div>}
      {actionMsg && <div className="panel" role="status"><p className="muted">{actionMsg}</p></div>}

      <section className="panel">
        <h2>New plan</h2>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Plan title, e.g. Week 42 milling batch" style={{ width: '100%', marginBottom: 8 }} />
        {items.map((it, i) => (
          <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
            <input value={it.task_name} onChange={(e) => setItems((l) => l.map((x, j) => (j === i ? { ...x, task_name: e.target.value } : x)))} placeholder="Task name *" style={{ flex: 2, minWidth: 160 }} />
            <input value={it.required_skill} onChange={(e) => setItems((l) => l.map((x, j) => (j === i ? { ...x, required_skill: e.target.value } : x)))} placeholder="Skill" style={{ flex: 1, minWidth: 120 }} />
            <input value={it.machine_type} onChange={(e) => setItems((l) => l.map((x, j) => (j === i ? { ...x, machine_type: e.target.value } : x)))} placeholder="Machine type" style={{ flex: 1, minWidth: 120 }} />
            <select value={it.priority} onChange={(e) => setItems((l) => l.map((x, j) => (j === i ? { ...x, priority: e.target.value } : x)))}>
              {['LOW', 'NORMAL', 'HIGH', 'URGENT'].map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
            <button type="button" className="btn-small" onClick={() => setItems((l) => l.filter((_, j) => j !== i))} disabled={items.length <= 1}>✕</button>
          </div>
        ))}
        <div style={{ display: 'flex', gap: 8 }}>
          <button type="button" className="btn-small" onClick={() => setItems((l) => [...l, { ...EMPTY_ITEM }])}>+ Item</button>
          <button type="button" className="btn-primary" onClick={handleCreate} disabled={busy === 'create'}>{busy === 'create' ? 'Drafting…' : 'Draft plan'}</button>
        </div>
      </section>

      <section className="panel">
        <h2>All plans</h2>
        {loading ? <p className="muted">Loading…</p> : plans.length === 0 ? <p className="muted">No plans yet. Draft the first one above.</p> : (
          <table className="data-table">
            <thead><tr><th>Title</th><th>Status</th><th>Created</th><th>Open</th></tr></thead>
            <tbody>
              {plans.map((p) => (
                <tr key={p.id} style={selected?.id === p.id ? { background: 'var(--accent-dim)' } : undefined}>
                  <td className="cell-strong">{p.title}</td>
                  <td><StatusBadge tone={toneForPlan(p.status)}>{p.status}</StatusBadge></td>
                  <td className="cell-mono muted">{p.created_at ? new Date(p.created_at).toLocaleDateString() : '—'}</td>
                  <td><button type="button" className="btn-small" onClick={() => openPlan(p)}>Open</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {selected && (
        <section className="panel">
          <h2>{selected.title} <StatusBadge tone={toneForPlan(selected.status)}>{selected.status}</StatusBadge></h2>
          <div className="no-print" style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
            {selected.status === 'DRAFT' && (
              <button type="button" className="btn-primary" disabled={busy === 'approve'} onClick={() => run('approve', () => api.approvePlan(selected.id), 'Approved — tasks created.')}>Approve (create tasks)</button>
            )}
            {['APPROVED', 'DISPATCHED'].includes(selected.status) && (
              <>
                <button type="button" className="btn-secondary" disabled={busy === 'suggest'} onClick={handleSuggest}>{busy === 'suggest' ? 'Ranking…' : '✦ AI-suggest pairings'}</button>
                <button type="button" className="btn-primary" disabled={busy === 'dispatch'} onClick={() => run('dispatch', () => api.dispatchPlan(selected.id), (r) => `Dispatched: ${r.dispatched} sent · ${r.skipped} skipped · ${r.unassigned} need staffing · push ${r.push_sent}.`)}>Dispatch to workers</button>
              </>
            )}
          </div>
          <table className="data-table">
            <thead><tr><th>Assignment</th><th>Status</th><th>Worker</th><th>AI suggestion</th><th>Apply</th></tr></thead>
            <tbody>
              {assignments.map((a) => {
                const s = sugById[a.id];
                return (
                  <tr key={a.id}>
                    <td className="cell-mono">{a.id.slice(0, 8)}</td>
                    <td><StatusBadge tone={a.status === 'UNASSIGNED' ? 'warn' : 'info'}>{a.status}</StatusBadge></td>
                    <td className="muted">{a.employee_id ? a.employee_id.slice(0, 8) : '—'}</td>
                    <td>
                      {!s ? <span className="muted">—</span> : s.status === 'UNASSIGNABLE' ? (
                        <span className="muted">{(s.reasons || []).join('; ') || 'No fit'}</span>
                      ) : (
                        <span><span className="cell-mono">{(s.employee_id || '').slice(0, 8)}</span>{' '}
                          <span className="muted">score {Number(s.score).toFixed(2)} · {(s.reasons || []).slice(0, 2).join('; ')}</span></span>
                      )}
                    </td>
                    <td>
                      {s && s.status === 'SUGGESTED' ? (
                        <button type="button" className="btn-small" disabled={busy === `apply-${a.id}`} onClick={() => handleApply(s)}>
                          {busy === `apply-${a.id}` ? '…' : 'Apply'}
                        </button>
                      ) : <span className="muted">—</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      )}
      </>
      )}
    </div>
  );
}
