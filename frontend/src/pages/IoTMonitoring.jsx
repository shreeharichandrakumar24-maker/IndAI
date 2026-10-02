import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../services/api';
import StatCard from '../components/StatCard';
import StatusBadge from '../components/StatusBadge';
import TelemetryFilters from '../components/iot/TelemetryFilters';
import MachineTelemetryGrid from '../components/iot/MachineTelemetryGrid';
import TelemetryDetails from '../components/iot/TelemetryDetails';
import RefreshBar from '../components/RefreshBar';
import useAutoRefresh from '../hooks/useAutoRefresh';
import {
  POLL_INTERVAL_MS,
  formatDateTime,
  toneForTelemetryStatus,
} from '../components/iot/telemetryUtils';

const HISTORY_LIMIT = 20;

export default function IoTMonitoring({ focusMachineId }) {
  const [machines, setMachines] = useState([]);
  const [latestById, setLatestById] = useState({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [pollNote, setPollNote] = useState('');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  const [selected, setSelected] = useState(null);
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState('');
  const selectedRef = useRef(null);
  useEffect(() => {
    selectedRef.current = selected;
  }, [selected]);

  // Latest telemetry for every machine. One small request per machine;
  // per-machine allSettled so one slow record never blocks the fleet view.
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

  const loadHistory = useCallback(async (machine) => {
    if (!machine) return;
    setHistoryLoading(true);
    setHistoryError('');
    try {
      const data = await api.telemetry(machine.id, HISTORY_LIMIT);
      setHistory(Array.isArray(data) ? data : []);
    } catch (err) {
      setHistoryError(err.message || 'Failed to load telemetry history');
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const initialLoad = useCallback(async () => {
    setLoading(true);
    setLoadError('');
    setPollNote('');
    try {
      const fleet = await api.machines();
      const list = Array.isArray(fleet) ? fleet : [];
      setMachines(list);
      const hadFailures = await refreshLatest(list.map((m) => m.id));
      if (hadFailures) setPollNote('Some machines did not report — retrying on the next poll.');
      setLastRefresh(new Date());
    } catch (err) {
      setLoadError(err.message || 'Failed to load machines');
    } finally {
      setLoading(false);
    }
  }, [refreshLatest]);

  useEffect(() => {
    initialLoad();
  }, [initialLoad]);

  // Modest polling: latest readings every 10s (the simulator's transmit
  // cadence), plus history for the selected machine. No sockets, no MQTT.
  // Driven by the shared auto-refresh hook (toggleable, hidden-tab aware).
  const pollOnce = useCallback(async () => {
    setRefreshing(true);
    try {
      const fleet = await api.machines().catch(() => null);
      const list = Array.isArray(fleet) ? fleet : null;
      if (list) setMachines(list);
      const ids = (list || []).map((m) => m.id);
      if (ids.length > 0) {
        const hadFailures = await refreshLatest(ids);
        setPollNote(hadFailures ? 'Some machines did not report — retrying on the next poll.' : '');
      }
      if (selectedRef.current) await loadHistory(selectedRef.current);
      setLastRefresh(new Date());
    } finally {
      setRefreshing(false);
    }
  }, [refreshLatest, loadHistory]);

  const refresher = useAutoRefresh(pollOnce, { intervalMs: POLL_INTERVAL_MS });

  const handleSelect = (machine) => {
    setSelected(machine);
    setHistory([]);
    setHistoryError('');
    if (machine) loadHistory(machine);
  };

  // Map navigation payload: auto-select the requested machine once loaded.
  useEffect(() => {
    if (focusMachineId && machines.length > 0) {
      const match = machines.find((m) => m.id === focusMachineId);
      if (match) handleSelect(match);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusMachineId, machines]);

  const handleManualRefresh = async () => {
    setRefreshing(true);
    try {
      await initialLoad();
      if (selectedRef.current) await loadHistory(selectedRef.current);
    } finally {
      setRefreshing(false);
    }
  };

  // Fleet overview — all values from loaded data, never hardcoded.
  const reporting = useMemo(
    () => machines.filter((m) => latestById[m.id]).length,
    [machines, latestById],
  );
  const latestTs = useMemo(() => {
    let max = null;
    for (const m of machines) {
      const ts = latestById[m.id]?.timestamp;
      if (ts && (!max || new Date(ts) > new Date(max))) max = ts;
    }
    return max;
  }, [machines, latestById]);
  const statusMix = useMemo(() => {
    const counts = {};
    for (const m of machines) {
      const s = latestById[m.id]?.machine_status;
      if (s) counts[s] = (counts[s] || 0) + 1;
    }
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }, [machines, latestById]);

  const reportedStatuses = useMemo(() => statusMix.map(([s]) => s), [statusMix]);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return machines.filter((m) => {
      if (statusFilter && (latestById[m.id]?.machine_status || '') !== statusFilter) return false;
      if (!q) return true;
      return (
        (m.name || '').toLowerCase().includes(q) ||
        String(m.id || '').toLowerCase().includes(q)
      );
    });
  }, [machines, search, statusFilter, latestById]);

  return (
    <div className="page">
      <RefreshBar auto={refresher.auto} onAuto={refresher.setAuto} onReload={refresher.refreshNow} refreshing={refresher.refreshing} lastRefresh={refresher.lastRefresh} />
      <div className="page-head">
        <div>
          <h2>IoT Monitoring</h2>
          <p className="page-desc">
            Live and recent machine telemetry received by IndAI — the same
            records the IoT simulator streams to the backend. Readings refresh
            automatically every 10 seconds.
          </p>
        </div>
        <button type="button" className="btn-secondary" onClick={handleManualRefresh} disabled={refreshing || loading}>
          {refreshing ? 'Refreshing…' : '↻ Refresh now'}
        </button>
      </div>

      <section className="stat-grid" aria-label="Telemetry figures" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        <StatCard label="Monitored Machines" value={machines.length} sub="fleet" loading={loading} />
        <StatCard label="Reporting" value={reporting} sub="with telemetry" loading={loading} />
        <StatCard label="Without Data" value={machines.length - reporting} sub="no telemetry yet" loading={loading} />
        <StatCard
          label="Latest Reading"
          value={latestTs ? formatDateTime(latestTs) : '—'}
          sub={refreshing ? 'refreshing…' : lastRefresh ? `polled ${lastRefresh.toLocaleTimeString()}` : 'live poll every 10s'}
          loading={loading}
        />
      </section>

      {loadError && (
        <div className="alert-banner" role="alert">
          {loadError}{' '}
          <button type="button" className="btn-small" onClick={initialLoad}>
            Retry
          </button>
        </div>
      )}
      {!loadError && pollNote && (
        <p className="muted" role="status">
          {pollNote}
        </p>
      )}

      {!loading && !loadError && statusMix.length > 0 && (
        <section className="panel" aria-label="Reported status mix">
          <h2>Reported Statuses</h2>
          <ul className="alert-list">
            {statusMix.map(([s, n]) => (
              <li key={s} className="alert-row">
                <StatusBadge tone={toneForTelemetryStatus(s)}>{s}</StatusBadge>
                <span className="alert-text">
                  {n} machine{n === 1 ? '' : 's'} reporting {s}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="panel">
        <h2>Machine Telemetry</h2>
        <TelemetryFilters
          search={search}
          onSearch={setSearch}
          status={statusFilter}
          onStatus={setStatusFilter}
          statuses={reportedStatuses}
        />
        {!loading && !loadError && (search.trim() || statusFilter) && visible.length === 0 && machines.length > 0 && (
          <p className="muted" style={{ marginTop: 12 }}>
            No machines match the current search/filter.
          </p>
        )}
        {!loadError && (
          <div style={{ marginTop: 12 }}>
            <MachineTelemetryGrid
              machines={visible}
              latestById={latestById}
              loading={loading}
              selectedId={selected?.id || null}
              onSelect={handleSelect}
            />
          </div>
        )}
      </section>

      {selected && (
        <TelemetryDetails
          machine={selected}
          history={history}
          historyLoading={historyLoading}
          historyError={historyError}
          onRetry={() => loadHistory(selected)}
          onClose={() => {
            setSelected(null);
            setHistory([]);
          }}
        />
      )}
    </div>
  );
}
