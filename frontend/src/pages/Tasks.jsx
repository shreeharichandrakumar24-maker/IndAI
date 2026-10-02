import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../services/api';
import RefreshBar from '../components/RefreshBar';
import useAutoRefresh from '../hooks/useAutoRefresh';
import StatCard from '../components/StatCard';
import StatusBadge from '../components/StatusBadge';
import TaskFilters from '../components/tasks/TaskFilters';
import TaskTable from '../components/tasks/TaskTable';
import TaskForm from '../components/tasks/TaskForm';
import { formatDateTime, isOpenTask, toneForTaskStatus } from '../components/tasks/taskWorkflow';

export default function Tasks({ onNavigate }) {
  const [tasks, setTasks] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [machines, setMachines] = useState([]);
  const [orders, setOrders] = useState([]);
  const [runs, setRuns] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('');
  const [assigneeFilter, setAssigneeFilter] = useState('');
  const [machineFilter, setMachineFilter] = useState('');
  const [orderFilter, setOrderFilter] = useState('');

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const [selected, setSelected] = useState(null);
  const [advancingId, setAdvancingId] = useState(null);
  const [actionError, setActionError] = useState('');

  const [confirmDelete, setConfirmDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    setLoadError('');
    try {
      const [t, e, m, o, r, inc] = await Promise.all([
        api.tasks(),
        api.employees().catch(() => []),
        api.machines().catch(() => []),
        api.orders().catch(() => []),
        api.production().catch(() => []),
        api.incidents().catch(() => []),
      ]);
      setTasks(Array.isArray(t) ? t : []);
      setEmployees(Array.isArray(e) ? e : []);
      setMachines(Array.isArray(m) ? m : []);
      setOrders(Array.isArray(o) ? o : []);
      setRuns(Array.isArray(r) ? r : []);
      setIncidents(Array.isArray(inc) ? inc : []);
    } catch (err) {
      setLoadError(err.message || 'Failed to load tasks');
    } finally {
      if (!quiet) setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const empById = useMemo(() => Object.fromEntries(employees.map((e) => [e.id, e])), [employees]);
  const machById = useMemo(() => Object.fromEntries(machines.map((m) => [m.id, m])), [machines]);
  const ordById = useMemo(() => Object.fromEntries(orders.map((o) => [o.id, o])), [orders]);

  const open = tasks.filter(isOpenTask);
  const pending = tasks.filter((t) => (t.status || '').toUpperCase() === 'PENDING').length;
  const inProgress = tasks.filter((t) => (t.status || '').toUpperCase() === 'IN_PROGRESS').length;
  const done = tasks.length - open.length;
  const nowMs = Date.now();
  const overdue = tasks.filter((t) => {
    if (!isOpenTask(t) || !t.deadline) return false;
    return new Date(t.deadline).getTime() < nowMs;
  }).length;
  const urgent = tasks.filter((t) => isOpenTask(t) && ['HIGH', 'URGENT'].includes((t.priority || '').toUpperCase())).length;

  const statuses = useMemo(
    () => [...new Set(tasks.map((t) => t.status).filter(Boolean))].sort(),
    [tasks],
  );

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return tasks.filter((t) => {
      if (statusFilter && t.status !== statusFilter) return false;
      if (priorityFilter && (t.priority || 'NORMAL') !== priorityFilter) return false;
      if (assigneeFilter && t.employee_id !== assigneeFilter) return false;
      if (machineFilter && t.machine_id !== machineFilter) return false;
      if (orderFilter && t.order_id !== orderFilter) return false;
      if (!q) return true;
      return (
        (t.name || '').toLowerCase().includes(q) ||
        (t.required_skill || '').toLowerCase().includes(q) ||
        (t.description || '').toLowerCase().includes(q)
      );
    });
  }, [tasks, search, statusFilter, priorityFilter, assigneeFilter, machineFilter, orderFilter]);

  const handleSubmit = async (payload) => {
    // Monitoring page: edit only. Creation lives in Orders -> Split.
    if (!editing) return;
    setSaving(true);
    setFormError('');
    try {
      await api.updateTask(editing.id, payload);
      setFormOpen(false);
      setEditing(null);
      await load();
    } catch (err) {
      setFormError(err.message || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const handleAdvance = async (task, next) => {
    setAdvancingId(task.id);
    setActionError('');
    try {
      await api.updateTask(task.id, { status: next, progress: next === 'DONE' ? 1.0 : task.progress });
      await load();
    } catch (err) {
      setActionError(err.message || 'Status change failed');
    } finally {
      setAdvancingId(null);
    }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    setDeleting(true);
    setDeleteError('');
    try {
      await api.deleteTask(confirmDelete.id);
      setConfirmDelete(null);
      setSelected(null);
      await load();
    } catch (err) {
      setDeleteError(err.message || 'Delete failed');
    } finally {
      setDeleting(false);
    }
  };

  const refresher = useAutoRefresh(load);

  return (
    <div className="page">
      <RefreshBar auto={refresher.auto} onAuto={refresher.setAuto} onReload={refresher.refreshNow} refreshing={refresher.refreshing} lastRefresh={refresher.lastRefresh} />
      <div className="page-head">
        <div>
          <h2>Tasks</h2>
          <p className="page-desc">Monitoring: who is doing what, on which machine, for which order. Move work PENDING → IN_PROGRESS → DONE with quick edit. New tasks are created in Orders → Split, not here.</p>
        </div>
      </div>

      <section className="stat-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
        <StatCard label="Total" value={tasks.length} sub="all tasks" loading={loading} />
        <StatCard label="Pending" value={pending} sub="not started" loading={loading} />
        <StatCard label="In Progress" value={inProgress} sub="being done" loading={loading} />
        <StatCard label="Completed" value={done} sub="done" loading={loading} />
        <StatCard label="Overdue" value={overdue} sub="open + past deadline" loading={loading} />
        <StatCard label="High priority" value={urgent} sub="open + urgent" loading={loading} />
      </section>

      {loadError && (
        <div className="alert-banner" role="alert">{loadError}{' '}
          <button type="button" className="btn-small" onClick={load}>Retry</button>
        </div>
      )}
      {actionError && <p className="form-errors" role="alert">{actionError}</p>}

      <section className="panel">
        <h2>All tasks</h2>
        <TaskFilters
          search={search} onSearch={setSearch}
          status={statusFilter} onStatus={setStatusFilter} statuses={statuses}
          priority={priorityFilter} onPriority={setPriorityFilter}
          assignee={assigneeFilter} onAssignee={setAssigneeFilter} employees={employees}
          machine={machineFilter} onMachine={setMachineFilter} machines={machines}
          order={orderFilter} onOrder={setOrderFilter} orders={orders}
        />
        {!loading && !loadError && (search.trim() || statusFilter || priorityFilter || assigneeFilter || machineFilter || orderFilter) && visible.length === 0 && tasks.length > 0 && (
          <p className="muted" style={{ marginTop: 12 }}>No tasks match the current search/filter.</p>
        )}
        <div style={{ marginTop: 12 }}>
          <TaskTable
            tasks={visible} loading={loading && !loadError}
            employees={empById} machines={machById} orders={ordById}
            onOpen={setSelected} onAdvance={handleAdvance} advancingId={advancingId}
          />
        </div>
      </section>

      {selected && (
        <div className="modal-backdrop" onClick={() => setSelected(null)}>
          <div className="modal" role="dialog" aria-modal="true" aria-label="Task details" onClick={(e) => e.stopPropagation()}>
            <div className="details-head">
              <h2>{selected.name}</h2>
              <button type="button" className="btn-small" onClick={() => setSelected(null)}>Close</button>
            </div>
            <div className="details-grid">
              <div><span className="detail-label">Status</span>
                <span className="detail-value"><StatusBadge tone={toneForTaskStatus(selected.status)}>{selected.status || 'PENDING'}</StatusBadge></span></div>
              <div><span className="detail-label">Priority</span>
                <span className="detail-value">{selected.priority || 'NORMAL'}</span></div>
              <div><span className="detail-label">Skill needed</span>
                <span className="detail-value">{selected.required_skill || '—'}</span></div>
              <div><span className="detail-label">Progress</span>
                <span className="detail-value cell-mono">{Math.round((selected.progress || 0) * 100)}%</span></div>
              <div><span className="detail-label">Assignee</span>
                <span className="detail-value">{selected.employee_id && empById[selected.employee_id] ? empById[selected.employee_id].name : 'Unassigned'}</span></div>
              <div><span className="detail-label">Machine</span>
                <span className="detail-value">{selected.machine_id && machById[selected.machine_id] ? machById[selected.machine_id].name : '—'}</span></div>
              <div><span className="detail-label">Order</span>
                <span className="detail-value">{selected.order_id && ordById[selected.order_id] ? ordById[selected.order_id].order_number : '—'}</span></div>
              <div><span className="detail-label">Deadline</span>
                <span className="detail-value cell-mono">{formatDateTime(selected.deadline)}</span></div>
            </div>
            {selected.description && <p className="muted" style={{ marginTop: 8 }}>{selected.description}</p>}
            {(() => {
              const linkedRun = runs.find((r) => r.task_id === selected.id) || null;
              const sameMachineIncidents = selected.machine_id
                ? incidents.filter((i) => i.machine_id === selected.machine_id && (i.status || 'OPEN').toUpperCase() !== 'RESOLVED')
                : [];
              const linkedOrder = selected.order_id && ordById[selected.order_id] ? ordById[selected.order_id] : null;
              return (
                <>
                  <h3 className="section-title">Linked production run</h3>
                  {linkedRun ? (
                    <p className="muted">{linkedRun.status} — {linkedRun.quantity_completed ?? 0}/{linkedRun.quantity_target ?? 0} units</p>
                  ) : (
                    <p className="muted">No production run linked to this task.</p>
                  )}
                  <h3 className="section-title">Open incidents on this machine ({sameMachineIncidents.length})</h3>
                  {sameMachineIncidents.length === 0 ? (
                    <p className="muted">None.</p>
                  ) : (
                    <ul className="task-list">
                      {sameMachineIncidents.map((i) => (
                        <li key={i.id} className="task-row">
                          <div className="task-main">
                            <span className="cell-strong">{i.severity}</span>
                            <span className="task-meta">{(i.description || '').slice(0, 120)}</span>
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                  <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
                    <button type="button" className="btn-secondary" onClick={() => { setEditing(selected); setSelected(null); setFormError(''); setFormOpen(true); }}>Edit</button>
                    {linkedOrder && onNavigate && (
                      <button type="button" className="btn-secondary" onClick={() => onNavigate('orders', { orderId: linkedOrder.id })}>
                        Open order {linkedOrder.order_number}
                      </button>
                    )}
                    <button type="button" className="btn-small" onClick={() => setConfirmDelete(selected)}>Delete…</button>
                  </div>
                </>
              );
            })()}
          </div>
        </div>
      )}

      {formOpen && (
        <TaskForm
          key={editing ? editing.id : 'new'}
          task={editing}
          employees={employees} machines={machines} orders={orders}
          saving={saving} apiError={formError}
          onSubmit={handleSubmit}
          onClose={() => { if (!saving) { setFormOpen(false); setEditing(null); } }}
        />
      )}

      {confirmDelete && (
        <div className="modal-backdrop" onClick={() => { if (!deleting) setConfirmDelete(null); }}>
          <div className="modal" role="dialog" aria-modal="true" aria-label="Confirm delete" onClick={(e) => e.stopPropagation()}>
            <h2>Delete “{confirmDelete.name}”?</h2>
            <p className="muted">This cannot be undone. Linked production runs keep a null task reference.</p>
            {deleteError && <p className="form-errors" role="alert">{deleteError}</p>}
            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <button type="button" className="btn-primary" disabled={deleting} onClick={handleDelete}>{deleting ? 'Deleting…' : 'Delete'}</button>
              <button type="button" className="btn-secondary" disabled={deleting} onClick={() => setConfirmDelete(null)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
