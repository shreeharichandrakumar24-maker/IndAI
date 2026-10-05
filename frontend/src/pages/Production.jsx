import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../services/api';
import RefreshBar from '../components/RefreshBar';
import useAutoRefresh from '../hooks/useAutoRefresh';
import StatCard from '../components/StatCard';
import ProductionFilters from '../components/production/ProductionFilters';
import ProductionTable from '../components/production/ProductionTable';
import ProductionForm from '../components/production/ProductionForm';
import ProductionDetails from '../components/production/ProductionDetails';

export default function Production({ presetFilter }) {
  const [runs, setRuns] = useState([]);
  const [orders, setOrders] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [machines, setMachines] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [refsError, setRefsError] = useState('');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  // Voice/typed preset from navigate(page, {filter}).
  useEffect(() => { if (presetFilter) setStatusFilter(presetFilter); }, [presetFilter]);
  const [orderFilter, setOrderFilter] = useState('');
  const [machineFilter, setMachineFilter] = useState('');

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const [detailsRun, setDetailsRun] = useState(null);

  const [confirmDelete, setConfirmDelete] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [deleteError, setDeleteError] = useState('');

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    setLoadError('');
    setRefsError('');
    try {
      // One batch, no per-row requests: FK display resolves from these lists.
      const [runData, orderData, taskData, machineData] = await Promise.all([
        api.production(),
        api.orders().catch(() => null),
        api.tasks().catch(() => null),
        api.machines().catch(() => null),
      ]);
      setRuns(Array.isArray(runData) ? runData : []);
      const missing = [];
      if (orderData === null) missing.push('orders');
      else setOrders(Array.isArray(orderData) ? orderData : []);
      if (taskData === null) missing.push('tasks');
      else setTasks(Array.isArray(taskData) ? taskData : []);
      if (machineData === null) missing.push('machines');
      else setMachines(Array.isArray(machineData) ? machineData : []);
      if (missing.length > 0) {
        setRefsError(`Reference data unavailable for: ${missing.join(', ')}. IDs are shown raw.`);
      }
    } catch (err) {
      setLoadError(err.message || 'Failed to load production runs');
    } finally {
      if (!quiet) setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const orderById = useMemo(() => Object.fromEntries(orders.map((o) => [o.id, o])), [orders]);
  const taskById = useMemo(() => Object.fromEntries(tasks.map((t) => [t.id, t])), [tasks]);
  const machineById = useMemo(() => Object.fromEntries(machines.map((m) => [m.id, m])), [machines]);

  // KPIs derived from loaded runs only — no hardcoded counts. Status cards
  // follow whatever distinct statuses the backend returns (default PLANNED).
  const statusCounts = useMemo(() => {
    const counts = {};
    for (const r of runs) {
      const s = (r.status || 'UNKNOWN').toUpperCase();
      counts[s] = (counts[s] || 0) + 1;
    }
    return counts;
  }, [runs]);

  const statusKeys = useMemo(() => Object.keys(statusCounts).sort(), [statusCounts]);

  const qtyTarget = useMemo(() => runs.reduce((a, r) => a + (Number(r.quantity_target) || 0), 0), [runs]);
  const qtyDone = useMemo(() => runs.reduce((a, r) => a + (Number(r.quantity_completed) || 0), 0), [runs]);

  const statuses = useMemo(
    () => [...new Set(runs.map((r) => r.status).filter(Boolean))].sort(),
    [runs],
  );

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return runs.filter((r) => {
      if (statusFilter && r.status !== statusFilter) return false;
      if (orderFilter && r.order_id !== orderFilter) return false;
      if (machineFilter && r.machine_id !== machineFilter) return false;
      if (!q) return true;
      return String(r.id || '').toLowerCase().includes(q);
    });
  }, [runs, search, statusFilter, orderFilter, machineFilter]);

  const openAdd = () => {
    setEditing(null);
    setFormError('');
    setFormOpen(true);
  };

  const openEdit = (run) => {
    setEditing(run);
    setFormError('');
    setFormOpen(true);
  };

  const handleSubmit = async (payload) => {
    setSaving(true);
    setFormError('');
    try {
      if (editing) {
        await api.updateProduction(editing.id, payload);
      } else {
        await api.createProduction(payload);
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
      await api.deleteProduction(confirmDelete.id);
      setConfirmDelete(null);
      if (detailsRun && detailsRun.id === confirmDelete.id) setDetailsRun(null);
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
          <h2>Production Execution</h2>
          <p className="page-desc">
            Track production runs linking orders, tasks and machines — the
            execution layer between planning and the factory floor. Open a run
            for its full order → run → task → machine chain.
          </p>
        </div>
        <button type="button" className="btn-primary" onClick={openAdd}>
          + Start Run
        </button>
      </div>

      <section
        className="stat-grid"
        aria-label="Production figures"
        style={{ gridTemplateColumns: `repeat(${Math.min(6, 2 + statusKeys.length)}, 1fr)` }}
      >
        <StatCard label="Total Runs" value={runs.length} sub="registered" loading={loading} />
        {statusKeys.map((s) => (
          <StatCard key={s} label={s} value={statusCounts[s]} sub="status" loading={loading} />
        ))}
        <StatCard label="Output" value={`${qtyDone} / ${qtyTarget}`} sub="units done / target" loading={loading} />
      </section>

      {loadError && (
        <div className="alert-banner" role="alert">
          {loadError}{' '}
          <button type="button" className="btn-small" onClick={load}>
            Retry
          </button>
        </div>
      )}
      {!loadError && refsError && (
        <div className="alert-banner" role="alert">
          {refsError}{' '}
          <button type="button" className="btn-small" onClick={load}>
            Retry
          </button>
        </div>
      )}

      <section className="panel">
        <h2>Production Runs</h2>
        <ProductionFilters
          search={search}
          onSearch={setSearch}
          status={statusFilter}
          onStatus={setStatusFilter}
          statuses={statuses}
          orderId={orderFilter}
          onOrderId={setOrderFilter}
          orders={orders}
          machineId={machineFilter}
          onMachineId={setMachineFilter}
          machines={machines}
        />
        {!loading && !loadError && (search.trim() || statusFilter || orderFilter || machineFilter) && visible.length === 0 && runs.length > 0 && (
          <p className="muted" style={{ marginTop: 12 }}>
            No production runs match the current search/filter.
          </p>
        )}
        {!loadError && (
          <div style={{ marginTop: 12 }}>
            <ProductionTable
              runs={visible}
              loading={loading}
              orderById={orderById}
              machineById={machineById}
              onOpen={setDetailsRun}
              onEdit={openEdit}
              onDelete={setConfirmDelete}
              deletingId={deletingId}
            />
          </div>
        )}
      </section>

      {formOpen && (
        <ProductionForm
          key={editing ? editing.id : 'new'}
          run={editing}
          orders={orders}
          tasks={tasks}
          machines={machines}
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

      {detailsRun && (
        <ProductionDetails
          run={detailsRun}
          orderById={orderById}
          taskById={taskById}
          machineById={machineById}
          onClose={() => setDetailsRun(null)}
        />
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
            <h2>Delete Production Run</h2>
            <p className="muted">
              Delete run{' '}
              <strong>{String(confirmDelete.id).slice(0, 8)}</strong>?
              Only this run record is removed — the linked order, task and machine are not
              affected. No other records depend on a production run. This cannot be undone.
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
