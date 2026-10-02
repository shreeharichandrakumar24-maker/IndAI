import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../services/api';
import RefreshBar from '../components/RefreshBar';
import useAutoRefresh from '../hooks/useAutoRefresh';
import StatCard from '../components/StatCard';
import StatusBadge from '../components/StatusBadge';
import { formatDateTime } from '../components/incidents/incidentWorkflow';

export default function Memory() {
  const [rows, setRows] = useState([]);
  const [machines, setMachines] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [machineFilter, setMachineFilter] = useState('');
  const [eventFilter, setEventFilter] = useState('');
  const [search, setSearch] = useState('');
  const [searched, setSearched] = useState(null); // server-side keyword results

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    setError('');
    setSearched(null);
    try {
      const params = {};
      if (machineFilter) params.machine_id = machineFilter;
      if (eventFilter) params.event_type = eventFilter;
      const [mem, mach] = await Promise.all([api.memory(params), api.machines().catch(() => [])]);
      setRows(Array.isArray(mem) ? mem : []);
      setMachines(Array.isArray(mach) ? mach : []);
    } catch (err) {
      setError(err.message || 'Failed to load factory memory');
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [machineFilter, eventFilter]);

  useEffect(() => { load(); }, [load]);

  const runSearch = async () => {
    const q = search.trim();
    if (!q) { setSearched(null); return; }
    setLoading(true);
    setError('');
    try {
      const params = { q };
      if (machineFilter) params.machine_id = machineFilter;
      if (eventFilter) params.event_type = eventFilter;
      const data = await api.memorySearch(params);
      setSearched(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message || 'Search failed');
    } finally {
      setLoading(false);
    }
  };

  const machineById = useMemo(() => Object.fromEntries(machines.map((m) => [m.id, m])), [machines]);
  const machineCode = (name) => { const m = /^M-\d{3}/.exec(name || ''); return m ? m[0] : String(name || '').slice(0, 12); };
  const eventTypes = useMemo(() => [...new Set(rows.map((r) => r.event_type).filter(Boolean))].sort(), [rows]);
  const refresher = useAutoRefresh(load);
  const decisions = rows.filter((r) => r.event_type === 'ADMIN_DECISION').length;

  const visible = useMemo(() => {
    if (searched !== null) return searched;
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((r) => ((r.title || '') + ' ' + (r.description || '') + ' ' + (r.resolution_action || '')).toLowerCase().includes(q));
  }, [rows, search, searched]);

  const KNOWN_EVENTS = ['ADMIN_DECISION', 'PLAN_DISPATCHED', 'INCIDENT_RESOLVED', 'SIMULATION_APPLIED', 'NOTE'];
  const chips = [...new Set([...KNOWN_EVENTS, ...eventTypes])];

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>Factory Memory</h2>
          <p className="page-desc">Read-only timeline of past events and admin decisions (what was approved, why, and what happened).</p>
        </div>
      </div>

      <section className="stat-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
        <StatCard label="Entries" value={rows.length} sub="newest first" loading={loading} />
        <StatCard label="Admin decisions" value={decisions} sub="approved / rejected" loading={loading} />
        <StatCard label="Event types" value={eventTypes.length} sub={eventTypes.join(', ') || '—'} loading={loading} />
      </section>

      {error && <div className="alert-banner" role="alert">{error} <button type="button" className="btn-small" onClick={load}>Retry</button></div>}

      <section className="panel">
        <h2>Timeline</h2>
        <RefreshBar auto={refresher.auto} onAuto={refresher.setAuto} onReload={refresher.refreshNow} refreshing={refresher.refreshing} lastRefresh={refresher.lastRefresh} />
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
          <input
            placeholder="Search title / notes… (Enter for server search)"
            value={search}
            onChange={(e) => { setSearch(e.target.value); if (!e.target.value.trim()) setSearched(null); }}
            onKeyDown={(e) => { if (e.key === 'Enter') runSearch(); }}
            style={{ minWidth: 200 }}
          />
          <button type="button" className="btn-small" onClick={runSearch}>Search</button>
          {searched !== null && <button type="button" className="btn-small" onClick={() => { setSearched(null); setSearch(''); }}>Clear</button>}
          <select value={machineFilter} onChange={(e) => setMachineFilter(e.target.value)}>
            <option value="">All machines</option>
            {machines.map((m) => <option key={m.id} value={m.id}>{machineCode(m.name)} · {m.name}</option>)}
          </select>
          <select value={eventFilter} onChange={(e) => setEventFilter(e.target.value)}>
            <option value="">All event types</option>
            {eventTypes.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
          {chips.map((t) => (
            <button
              key={t}
              type="button"
              className={eventFilter === t ? 'btn-primary' : 'btn-small'}
              onClick={() => setEventFilter((f) => (f === t ? '' : t))}
            >
              {t}
            </button>
          ))}
        </div>
        {loading ? <p className="muted">Loading…</p> : visible.length === 0 ? <p className="muted">No memory entries yet. Approve or reject an AI recommendation to write the first one.</p> : (
          <ul className="task-list">
            {visible.map((r) => (
              <li key={r.id} className="task-row">
                <div className="task-main">
                  <span className="cell-strong">{r.title}</span>
                  <span className="task-meta">
                    {r.machine_id && machineById[r.machine_id] ? `${machineCode(machineById[r.machine_id].name)} · ` : ''}
                    {r.order_id ? `order ${String(r.order_id).slice(0, 8)} · ` : ''}
                    {formatDateTime(r.created_at)}
                    {r.description ? ` — ${r.description.slice(0, 160)}` : ''}
                    {r.resolution_action ? ` · Action: ${r.resolution_action.slice(0, 160)}` : ''}
                  </span>
                </div>
                <div className="task-badges">
                  <StatusBadge tone={r.event_type === 'ADMIN_DECISION' ? 'info' : 'neutral'}>{r.event_type || 'EVENT'}</StatusBadge>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
