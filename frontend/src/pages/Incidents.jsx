import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../services/api';
import RefreshBar from '../components/RefreshBar';
import useAutoRefresh from '../hooks/useAutoRefresh';
import StatCard from '../components/StatCard';
import IncidentFilters from '../components/incidents/IncidentFilters';
import IncidentTable from '../components/incidents/IncidentTable';
import IncidentDetails from '../components/incidents/IncidentDetails';
import { isActiveIncident } from '../components/incidents/incidentWorkflow';

export default function Incidents({ focusIncidentId }) {
  const [incidents, setIncidents] = useState([]);
  const [machines, setMachines] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [severityFilter, setSeverityFilter] = useState('');
  const [machineFilter, setMachineFilter] = useState('');

  const [selected, setSelected] = useState(null);

  const [checking, setChecking] = useState(false);
  const [checkResult, setCheckResult] = useState(null);
  const [checkError, setCheckError] = useState('');

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    setLoadError('');
    try {
      const [incData, machData] = await Promise.all([
        api.incidents(),
        api.machines().catch(() => []),
      ]);
      setIncidents(Array.isArray(incData) ? incData : []);
      setMachines(Array.isArray(machData) ? machData : []);
    } catch (err) {
      setLoadError(err.message || 'Failed to load incidents');
    } finally {
      if (!quiet) setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Map navigation payload: auto-open the requested incident once loaded.
  useEffect(() => {
    if (focusIncidentId && incidents.length > 0) {
      const match = incidents.find((i) => i.id === focusIncidentId);
      if (match) setSelected(match);
    }
  }, [focusIncidentId, incidents]);

  const machineById = useMemo(() => Object.fromEntries(machines.map((m) => [m.id, m])), [machines]);

  const openCount = incidents.filter((i) => (i.status || 'OPEN').toUpperCase() === 'OPEN').length;
  const inProgressCount = incidents.filter((i) => (i.status || '').toUpperCase() === 'IN_PROGRESS').length;
  const resolvedCount = incidents.filter((i) => (i.status || '').toUpperCase() === 'RESOLVED').length;
  const criticalHigh = incidents.filter(
    (i) => isActiveIncident(i) && ['CRITICAL', 'HIGH'].includes((i.severity || '').toUpperCase()),
  ).length;

  const statuses = useMemo(
    () => [...new Set(incidents.map((i) => i.status).filter(Boolean))].sort(),
    [incidents],
  );
  const severities = useMemo(
    () => [...new Set(incidents.map((i) => i.severity).filter(Boolean))].sort(),
    [incidents],
  );

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return incidents.filter((i) => {
      if (statusFilter && i.status !== statusFilter) return false;
      if (severityFilter && i.severity !== severityFilter) return false;
      if (machineFilter && i.machine_id !== machineFilter) return false;
      if (!q) return true;
      return (
        (i.incident_type || '').toLowerCase().includes(q) ||
        (i.description || '').toLowerCase().includes(q)
      );
    });
  }, [incidents, search, statusFilter, severityFilter, machineFilter]);

  const handleCheckAll = async () => {
    setChecking(true);
    setCheckError('');
    setCheckResult(null);
    try {
      const result = await api.checkAllMachines();
      setCheckResult(result);
      await load();
    } catch (err) {
      setCheckError(err.message || 'Detection check failed');
    } finally {
      setChecking(false);
    }
  };

  const refresher = useAutoRefresh(load);

  return (
    <div className="page">
      <RefreshBar auto={refresher.auto} onAuto={refresher.setAuto} onReload={refresher.refreshNow} refreshing={refresher.refreshing} lastRefresh={refresher.lastRefresh} />
      <div className="page-head">
        <div>
          <h2>Incident Alerts</h2>
          <p className="page-desc">
            Abnormal-telemetry alerts raised by backend detection. Open an incident to inspect machine
            health, create linked maintenance, and resolve only once telemetry is normal again.
          </p>
        </div>
        <button type="button" className="btn-primary" onClick={handleCheckAll} disabled={checking || loading}>
          {checking ? 'Checking…' : '▸ Check All Machines'}
        </button>
      </div>

      <section className="stat-grid" aria-label="Incident figures" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        <StatCard label="Open" value={openCount} sub="need attention" loading={loading} />
        <StatCard label="In Progress" value={inProgressCount} sub="being handled" loading={loading} />
        <StatCard label="Resolved" value={resolvedCount} sub="closed" loading={loading} />
        <StatCard label="Critical / High" value={criticalHigh} sub="active alerts" loading={loading} />
      </section>

      {checkResult && (
        <div className="panel" role="status">
          <p className="muted">
            Detection check: {checkResult.checked} machines checked · {checkResult.abnormal} abnormal ·{' '}
            {checkResult.incidents_created} new incident(s) created. Duplicates are never created for
            machines that already have an open incident.
          </p>
        </div>
      )}
      {checkError && (
        <div className="alert-banner" role="alert">
          {checkError}{' '}
          <button type="button" className="btn-small" onClick={handleCheckAll}>
            Retry
          </button>
        </div>
      )}

      {loadError && (
        <div className="alert-banner" role="alert">
          {loadError}{' '}
          <button type="button" className="btn-small" onClick={load}>
            Retry
          </button>
        </div>
      )}

      <section className="panel">
        <h2>Incidents</h2>
        <IncidentFilters
          search={search}
          onSearch={setSearch}
          status={statusFilter}
          onStatus={setStatusFilter}
          statuses={statuses}
          severity={severityFilter}
          onSeverity={setSeverityFilter}
          severities={severities}
          machineId={machineFilter}
          onMachineId={setMachineFilter}
          machines={machines}
        />
        {!loading && !loadError && (search.trim() || statusFilter || severityFilter || machineFilter) && visible.length === 0 && incidents.length > 0 && (
          <p className="muted" style={{ marginTop: 12 }}>
            No incidents match the current search/filter.
          </p>
        )}
        {!loadError && (
          <div style={{ marginTop: 12 }}>
            <IncidentTable incidents={visible} loading={loading} machineById={machineById} onOpen={setSelected} />
          </div>
        )}
      </section>

      {selected && (
        <IncidentDetails
          key={selected.id}
          incident={selected}
          machine={machineById[selected.machine_id] || null}
          onClose={() => setSelected(null)}
          onChanged={load}
        />
      )}
    </div>
  );
}
