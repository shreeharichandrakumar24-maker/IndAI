import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../services/api';
import RefreshBar from '../components/RefreshBar';
import useAutoRefresh from '../hooks/useAutoRefresh';
import StatCard from '../components/StatCard';
import MachineFilters from '../components/machines/MachineFilters';
import MachineTable from '../components/machines/MachineTable';
import MachineForm from '../components/machines/MachineForm';
import MachineDetails from '../components/machines/MachineDetails';

export default function Machines({ focusMachineId, presetFilter }) {
  const [machines, setMachines] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  // Voice/typed preset from navigate(page, {filter}).
  useEffect(() => { if (presetFilter) setStatusFilter(presetFilter); }, [presetFilter]);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const [detailsMachine, setDetailsMachine] = useState(null);

  const [confirmDelete, setConfirmDelete] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [deleteError, setDeleteError] = useState('');

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    setLoadError('');
    try {
      const data = await api.machines();
      setMachines(Array.isArray(data) ? data : []);
    } catch (err) {
      setLoadError(err.message || 'Failed to load machines');
    } finally {
      if (!quiet) setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Map navigation payload: auto-open details for the requested machine.
  useEffect(() => {
    if (focusMachineId && machines.length > 0) {
      const match = machines.find((m) => m.id === focusMachineId);
      if (match) setDetailsMachine(match);
    }
  }, [focusMachineId, machines]);

  // KPI values derived from the loaded records only — no hardcoded counts.
  // Status cards follow whatever distinct status values the backend returns
  // (the seeded fleet reports OPERATIONAL; live telemetry reports
  // RUNNING/IDLE/MAINTENANCE/STOPPED via machine_status in Details).
  const statusCounts = useMemo(() => {
    const counts = {};
    for (const m of machines) {
      const s = (m.status || 'UNKNOWN').toUpperCase();
      counts[s] = (counts[s] || 0) + 1;
    }
    return counts;
  }, [machines]);

  const statusKeys = useMemo(() => Object.keys(statusCounts).sort(), [statusCounts]);

  const healthy = useMemo(
    () => machines.filter((m) => (m.health_status || '').toUpperCase() === 'GOOD').length,
    [machines],
  );

  const statuses = useMemo(
    () => [...new Set(machines.map((m) => m.status).filter(Boolean))].sort(),
    [machines],
  );

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return machines.filter((m) => {
      if (statusFilter && m.status !== statusFilter) return false;
      if (!q) return true;
      return (
        (m.name || '').toLowerCase().includes(q) ||
        (m.machine_type || '').toLowerCase().includes(q) ||
        (m.location || '').toLowerCase().includes(q) ||
        String(m.id || '').toLowerCase().includes(q)
      );
    });
  }, [machines, search, statusFilter]);

  const openAdd = () => {
    setEditing(null);
    setFormError('');
    setFormOpen(true);
  };

  const openEdit = (machine) => {
    setEditing(machine);
    setFormError('');
    setFormOpen(true);
  };

  const handleSubmit = async (payload) => {
    setSaving(true);
    setFormError('');
    try {
      if (editing) {
        await api.updateMachine(editing.id, payload);
      } else {
        await api.createMachine(payload);
      }
      setFormOpen(false);
      setEditing(null);
      await load();
    } catch (err) {
      setFormError(err.message || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    setDeletingId(confirmDelete.id);
    setDeleteError('');
    try {
      await api.deleteMachine(confirmDelete.id);
      setConfirmDelete(null);
      if (detailsMachine && detailsMachine.id === confirmDelete.id) setDetailsMachine(null);
      await load();
    } catch (err) {
      setDeleteError(err.message || 'Delete failed');
    } finally {
      setDeletingId(null);
    }
  };

  const refresher = useAutoRefresh(load);

  return (
    <div className="page">
      <RefreshBar auto={refresher.auto} onAuto={refresher.setAuto} onReload={refresher.refreshNow} refreshing={refresher.refreshing} lastRefresh={refresher.lastRefresh} />
      <div className="page-head">
        <div>
          <h2>Machine Fleet Control</h2>
          <p className="page-desc">
            Administer the equipment fleet and inspect live IoT telemetry per
            machine — the same records the simulator streams against. Open a
            machine&apos;s details to see its latest sensor readings.
          </p>
        </div>
        <button type="button" className="btn-primary" onClick={openAdd}>
          + Add Machine
        </button>
      </div>

      <section
        className="stat-grid"
        aria-label="Machine figures"
        style={{ gridTemplateColumns: `repeat(${Math.min(6, 2 + statusKeys.length)}, 1fr)` }}
      >
        <StatCard label="Total Machines" value={machines.length} sub="registered" loading={loading} />
        {statusKeys.map((s) => (
          <StatCard key={s} label={s} value={statusCounts[s]} sub="status" loading={loading} />
        ))}
        <StatCard label="Health Good" value={healthy} sub="reporting GOOD" loading={loading} />
      </section>

      {loadError && (
        <div className="alert-banner" role="alert">
          {loadError}{' '}
          <button type="button" className="btn-small" onClick={load}>
            Retry
          </button>
        </div>
      )}

      <section className="panel">
        <h2>Machine Fleet</h2>
        <MachineFilters
          search={search}
          onSearch={setSearch}
          status={statusFilter}
          onStatus={setStatusFilter}
          statuses={statuses}
        />
        {!loading && !loadError && (search.trim() || statusFilter) && visible.length === 0 && machines.length > 0 && (
          <p className="muted" style={{ marginTop: 12 }}>
            No machines match the current search/filter.
          </p>
        )}
        {!loadError && (
          <div style={{ marginTop: 12 }}>
            <MachineTable
              machines={visible}
              loading={loading}
              onOpen={setDetailsMachine}
              onEdit={openEdit}
              onDelete={setConfirmDelete}
              deletingId={deletingId}
            />
          </div>
        )}
      </section>

      {formOpen && (
        <MachineForm
          key={editing ? editing.id : 'new'}
          machine={editing}
          saving={saving}
          apiError={formError}
          onSubmit={handleSubmit}
          onClose={() => {
            if (!saving) {
              setFormOpen(false);
              setEditing(null);
            }
          }}
        />
      )}

      {detailsMachine && (
        <MachineDetails machine={detailsMachine} onClose={() => setDetailsMachine(null)} />
      )}

      {confirmDelete && (
        <div className="modal-backdrop" onClick={() => (deletingId ? null : setConfirmDelete(null))}>
          <div
            className="modal modal-narrow"
            role="dialog"
            aria-modal="true"
            aria-label="Confirm deletion"
            onClick={(e) => e.stopPropagation()}
          >
            <h2>Delete Machine</h2>
            <p className="muted">
              Remove <strong>{confirmDelete.name}</strong> (
              {confirmDelete.machine_type || 'unknown type'}) from the fleet? Its telemetry and
              maintenance records will be permanently deleted, and it will be unlinked from
              related tasks, production runs, incidents and factory memory. This cannot be
              undone.
            </p>
            {deleteError && (
              <p className="form-errors" role="alert" style={{ marginTop: 12 }}>
                {deleteError}
              </p>
            )}
            <div className="modal-actions">
              <button
                type="button"
                className="btn-secondary"
                disabled={!!deletingId}
                onClick={() => setConfirmDelete(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn-small btn-danger"
                style={{ padding: '10px 18px', fontSize: '0.88rem' }}
                disabled={!!deletingId}
                onClick={handleDelete}
              >
                {deletingId ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
