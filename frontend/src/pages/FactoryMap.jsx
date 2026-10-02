import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../services/api';
import StatCard from '../components/StatCard';
import StatusBadge from '../components/StatusBadge';
import FactoryMapSvg from '../components/map/FactoryMapSvg';
import MachineSidePanel from '../components/map/MachineSidePanel';
import RefreshBar from '../components/RefreshBar';
import useAutoRefresh from '../hooks/useAutoRefresh';
import {
  STALE_MS,
  machineCode,
  nodeState,
  resolveLayout,
  thresholdsFor,
} from '../components/map/mapUtils';

const POLL_MS = 10000;

function isOpenIncident(i) {
  return (i.status || 'OPEN').toUpperCase() !== 'RESOLVED';
}

// Visual floor plan for navigating machines. Deterministic only: node color
// comes from machine status/health, telemetry freshness, OPEN incidents and
// the rule-based abnormal check (same thresholds as the backend detector).
export default function FactoryMap({ onNavigate }) {
  const [machines, setMachines] = useState([]);
  const [latestById, setLatestById] = useState({});
  const [incidents, setIncidents] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [runs, setRuns] = useState([]);
  const [orders, setOrders] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [pollNote, setPollNote] = useState('');
  const [lastRefresh, setLastRefresh] = useState(null);

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [orderFocus, setOrderFocus] = useState('');
  const [selectedCode, setSelectedCode] = useState(null);

  const [editMode, setEditMode] = useState(false);
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');

  const refreshLatest = useCallback(async (ids) => {
    const results = await Promise.allSettled(ids.map((id) => api.latestTelemetry(id)));
    setLatestById((prev) => {
      const next = { ...prev };
      ids.forEach((id, i) => {
        if (results[i].status === 'fulfilled') next[id] = results[i].value;
      });
      return next;
    });
    return results.some((r) => r.status === 'rejected');
  }, []);

  const loadAll = useCallback(async (first = false) => {
    if (first) setLoading(true);
    setLoadError('');
    try {
      const [fleet, inc, tsk, prd, ord, emp, prof] = await Promise.allSettled([
        api.machines(),
        api.incidents(),
        api.tasks(),
        api.production(),
        api.orders(),
        api.employees().catch(() => []),
        api.profile().catch(() => null),
      ]);
      if (fleet.status === 'fulfilled' && Array.isArray(fleet.value)) {
        setMachines(fleet.value);
        const hadFailures = await refreshLatest(fleet.value.map((m) => m.id));
        if (hadFailures) setPollNote('Some machines did not report — retrying on the next poll.');
      } else if (first) {
        throw new Error('Failed to load machines');
      }
      if (inc.status === 'fulfilled') setIncidents(Array.isArray(inc.value) ? inc.value : []);
      if (tsk.status === 'fulfilled') setTasks(Array.isArray(tsk.value) ? tsk.value : []);
      if (prd.status === 'fulfilled') setRuns(Array.isArray(prd.value) ? prd.value : []);
      if (ord.status === 'fulfilled') setOrders(Array.isArray(ord.value) ? ord.value : []);
      if (emp.status === 'fulfilled') setEmployees(Array.isArray(emp.value) ? emp.value : []);
      if (prof.status === 'fulfilled' && prof.value) setProfile(prof.value);
      setLastRefresh(new Date());
    } catch (err) {
      if (first) setLoadError(err.message || 'Failed to load factory map');
    } finally {
      if (first) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    loadAll(true);
  }, [loadAll]);

  // Shared auto-refresh (pauses while editing layout so drags never jump).
  const refresher = useAutoRefresh(
    useCallback(() => loadAll(false), [loadAll]),
    { intervalMs: POLL_MS, paused: editMode },
  );

  const layout = useMemo(
    () => resolveLayout(profile?.profile?.layout, machines),
    [profile, machines],
  );
  const positions = editMode && draft ? draft : layout.positions;

  const byId = useMemo(() => ({
    employees: Object.fromEntries(employees.map((e) => [e.id, e])),
    orders: Object.fromEntries(orders.map((o) => [o.id, o])),
  }), [employees, orders]);

  const openByMachine = useMemo(() => {
    const map = {};
    for (const i of incidents) {
      if (!isOpenIncident(i) || !i.machine_id) continue;
      (map[i.machine_id] = map[i.machine_id] || []).push(i);
    }
    return map;
  }, [incidents]);

  const nowMs = Date.now();
  const nodes = useMemo(() => machines.map((m) => {
    const code = machineCode(m.name) || String(m.id).slice(0, 8);
    const pos = positions[code] || { x: 60, y: 60, zone_id: null };
    const th = thresholdsFor(profile?.profile, m.machine_type);
    const st = nodeState(m, latestById[m.id], (openByMachine[m.id] || []).length, th, nowMs);
    return {
      code, x: pos.x, y: pos.y, machine: m, machineType: m.machine_type,
      machineName: m.name, tone: st.tone, stateLabel: st.label, alert: st.alert,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [machines, positions, latestById, openByMachine, profile]);

  const focusMachineIds = useMemo(() => {
    if (!orderFocus) return null;
    const ids = new Set();
    for (const r of runs) if (r.order_id === orderFocus && r.machine_id) ids.add(r.machine_id);
    for (const t of tasks) if (t.order_id === orderFocus && t.machine_id) ids.add(t.machine_id);
    return ids;
  }, [orderFocus, runs, tasks]);

  const focusChain = useMemo(() => {
    if (!orderFocus) return null;
    const order = byId.orders[orderFocus];
    const chainTasks = tasks.filter((t) => t.order_id === orderFocus);
    const codes = [...new Set(chainTasks.map((t) => {
      const m = machines.find((x) => x.id === t.machine_id);
      return m ? (machineCode(m.name) || m.name) : null;
    }).filter(Boolean))];
    return { order, tasks: chainTasks, codes };
  }, [orderFocus, tasks, machines, byId]);

  const visibleNodes = useMemo(() => {
    const q = search.trim().toLowerCase();
    return nodes.filter((n) => {
      if (q && !(n.code.toLowerCase().includes(q) || (n.machineName || '').toLowerCase().includes(q))) return false;
      if (statusFilter === 'abnormal' && n.tone !== 'bad') return false;
      if (statusFilter === 'stale' && n.tone !== 'stale') return false;
      if (statusFilter === 'running') {
        const st = (latestById[n.machine.id]?.machine_status || '').toUpperCase();
        if (st !== 'RUNNING' || n.tone === 'bad') return false;
      }
      if (statusFilter === 'idle') {
        const st = (latestById[n.machine.id]?.machine_status || '').toUpperCase();
        if (st !== 'IDLE' || n.tone === 'bad') return false;
      }
      return true;
    });
  }, [nodes, search, statusFilter, latestById]);

  const selected = useMemo(() => {
    const node = nodes.find((n) => n.code === selectedCode);
    if (!node) return null;
    const m = node.machine;
    const run = runs.find((r) => r.machine_id === m.id && ['IN_PROGRESS', 'RUNNING'].includes((r.status || '').toUpperCase()))
      || runs.find((r) => r.machine_id === m.id) || null;
    const task = (run?.task_id && tasks.find((t) => t.id === run.task_id))
      || tasks.find((t) => t.machine_id === m.id && (t.status || '').toUpperCase() === 'IN_PROGRESS') || null;
    const order = (task?.order_id && byId.orders[task.order_id]) || (run?.order_id && byId.orders[run.order_id]) || null;
    const employee = (task?.employee_id && byId.employees[task.employee_id]) || null;
    return {
      code: node.code, machine: m, latest: latestById[m.id] || null,
      tone: node.tone, stateLabel: node.stateLabel,
      run, task, order, employee, incidents: openByMachine[m.id] || [],
    };
  }, [nodes, selectedCode, runs, tasks, byId, latestById, openByMachine]);

  const alertCount = nodes.filter((n) => n.alert).length;

  const startEdit = () => {
    setDraft(Object.fromEntries(Object.entries(layout.positions).map(([k, v]) => [k, { ...v }])));
    setEditMode(true);
    setSaveMsg('');
  };
  const cancelEdit = () => {
    setDraft(null);
    setEditMode(false);
    setSaveMsg('');
  };
  const moveNode = (code, x, y) => {
    setDraft((d) => ({ ...d, [code]: { ...(d[code] || {}), x, y } }));
  };
  const persistLayout = async (newPositions, msg) => {
    setSaving(true);
    setSaveMsg('');
    try {
      const current = await api.profile();
      const prof = current.profile || {};
      await api.saveProfile({ ...prof, layout: { width: layout.width, height: layout.height, zones: layout.zones, machines: newPositions } });
      const fresh = await api.profile();
      setProfile(fresh);
      setSaveMsg(msg);
      setDraft(null);
      setEditMode(false);
    } catch (err) {
      setSaveMsg(`Save failed: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };
  const resetPreset = async () => {
    setSaving(true);
    try {
      const preset = await api.presetProfile();
      const layoutPreset = (preset.profile || preset).layout;
      if (!layoutPreset) throw new Error('Preset has no layout');
      await persistLayout(layoutPreset.machines, 'Reset to preset layout.');
    } catch (err) {
      setSaveMsg(`Reset failed: ${err.message}`);
      setSaving(false);
    }
  };

  return (
    <div className="page">
      <RefreshBar auto={refresher.auto} onAuto={refresher.setAuto} onReload={refresher.refreshNow} refreshing={refresher.refreshing} lastRefresh={refresher.lastRefresh} />
      <div className="page-head">
        <div>
          <h2>Factory Map</h2>
          <p className="page-desc">The whole floor at a glance. Click any machine to inspect and navigate.</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {!editMode ? (
            <button type="button" className="btn-secondary" onClick={startEdit}>✎ Edit layout</button>
          ) : (
            <>
              <button type="button" className="btn-primary" disabled={saving} onClick={() => persistLayout(draft, 'Layout saved.')}>
                {saving ? 'Saving…' : 'Save layout'}
              </button>
              <button type="button" className="btn-secondary" disabled={saving} onClick={cancelEdit}>Cancel</button>
            </>
          )}
        </div>
      </div>

      <section className="stat-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        <StatCard label="Machines" value={nodes.length} sub={`${layout.zones.length} zones`} loading={loading} />
        <StatCard label="Alerts" value={alertCount} sub="rule-based abnormal" loading={loading} />
        <StatCard label="Open incidents" value={incidents.filter(isOpenIncident).length} sub="fleet-wide" loading={loading} />
        <StatCard label="Updated" value={lastRefresh ? lastRefresh.toLocaleTimeString() : '—'} sub={pollNote || '10s poll'} loading={loading} />
      </section>

      {loadError && (
        <div className="alert-banner" role="alert">{loadError}{' '}
          <button type="button" className="btn-small" onClick={() => loadAll(true)}>Retry</button>
        </div>
      )}
      {saveMsg && <div className="panel" role="status"><p className="muted">{saveMsg}</p></div>}

      <section className="panel">
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
          <input placeholder="Search code / name…" value={search} onChange={(e) => setSearch(e.target.value)} style={{ minWidth: 180 }} />
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">All statuses</option>
            <option value="abnormal">Abnormal</option>
            <option value="running">Running</option>
            <option value="idle">Idle</option>
            <option value="stale">Offline / stale</option>
          </select>
          <select value={orderFocus} onChange={(e) => setOrderFocus(e.target.value)}>
            <option value="">Order focus: off</option>
            {orders.map((o) => <option key={o.id} value={o.id}>{o.order_number} ({o.status})</option>)}
          </select>
          {(search || statusFilter || orderFocus) && (
            <button type="button" className="btn-small" onClick={() => { setSearch(''); setStatusFilter(''); setOrderFocus(''); }}>Clear</button>
          )}
        </div>

        {focusChain && (
          <p className="muted" style={{ marginBottom: 8 }}>
            Chain: <b>{focusChain.order?.order_number || '?'}</b>
            {' → Tasks: '}{focusChain.tasks.length > 0 ? focusChain.tasks.map((t) => t.name).join(', ') : 'none'}
            {' → Machines: '}{focusChain.codes.length > 0 ? focusChain.codes.join(', ') : 'none'}
          </p>
        )}

        {loading ? <p className="muted">Loading map…</p> : (
          <FactoryMapSvg
            width={layout.width}
            height={layout.height}
            zones={layout.zones}
            nodes={visibleNodes}
            selectedCode={selectedCode}
            dimmed={focusMachineIds}
            editMode={editMode}
            onSelect={setSelectedCode}
            onMove={moveNode}
          />
        )}

        <p className="muted" style={{ marginTop: 8 }}>
          Legend: <span style={{ color: '#22c55e' }}>●</span> normal ·{' '}
          <span style={{ color: '#ef4444' }}>●</span> abnormal / open incident (rule-based, pulsing ring) ·{' '}
          <span style={{ color: '#64748b' }}>●</span> stale (&gt;{Math.round(STALE_MS / 1000)}s) or no data ·{' '}
          ◆ selected. Last updated {lastRefresh ? lastRefresh.toLocaleTimeString() : '—'}.
        </p>
      </section>

      <MachineSidePanel data={selected} onNavigate={onNavigate} onClose={() => setSelectedCode(null)} />

      {editMode && (
        <div className="panel" role="status">
          <p className="muted">Drag nodes to reposition (snaps to grid, touch supported). Save persists via the profile; polling is paused while editing.</p>
          <button type="button" className="btn-small" disabled={saving} onClick={resetPreset}>Reset to preset layout</button>
        </div>
      )}
    </div>
  );
}
