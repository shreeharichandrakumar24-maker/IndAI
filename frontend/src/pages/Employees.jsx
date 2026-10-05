import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../services/api';
import RefreshBar from '../components/RefreshBar';
import useAutoRefresh from '../hooks/useAutoRefresh';
import StatCard from '../components/StatCard';
import EmployeeFilters from '../components/employees/EmployeeFilters';
import EmployeeTable from '../components/employees/EmployeeTable';
import EmployeeForm from '../components/employees/EmployeeForm';
import WorkerLoginModal from '../components/employees/WorkerLoginModal';

export default function Employees({ presetFilter }) {
  const [employees, setEmployees] = useState([]);
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

  const [confirmDelete, setConfirmDelete] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [deleteError, setDeleteError] = useState('');
  const [logins, setLogins] = useState({});
  const [loginFor, setLoginFor] = useState(null);

  const loadLogins = useCallback(async (list) => {
    const results = await Promise.allSettled((list || []).map((e) => api.workerLoginInfo(e.id)));
    const map = {};
    (list || []).forEach((e, i) => {
      if (results[i].status === 'fulfilled') map[e.id] = results[i].value;
    });
    setLogins(map);
  }, []);

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    setLoadError('');
    try {
      const data = await api.employees();
      const list = Array.isArray(data) ? data : [];
      setEmployees(list);
      loadLogins(list);
    } catch (err) {
      setLoadError(err.message || 'Failed to load employees');
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [loadLogins]);

  useEffect(() => {
    load();
  }, [load]);

  const active = employees.filter((e) => (e.status || '').toUpperCase() === 'ACTIVE');
  const statuses = useMemo(
    () => [...new Set(employees.map((e) => e.status).filter(Boolean))].sort(),
    [employees],
  );

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return employees.filter((e) => {
      if (statusFilter && e.status !== statusFilter) return false;
      if (!q) return true;
      return (
        (e.name || '').toLowerCase().includes(q) ||
        (e.role || '').toLowerCase().includes(q) ||
        String(e.id || '').toLowerCase().includes(q)
      );
    });
  }, [employees, search, statusFilter]);

  const openAdd = () => {
    setEditing(null);
    setFormError('');
    setFormOpen(true);
  };

  const openEdit = (employee) => {
    setEditing(employee);
    setFormError('');
    setFormOpen(true);
  };

  const handleSubmit = async (payload) => {
    setSaving(true);
    setFormError('');
    try {
      let saved = editing;
      if (editing) {
        await api.updateEmployee(editing.id, payload);
      } else {
        saved = await api.createEmployee(payload);
      }
      setFormOpen(false);
      setEditing(null);
      await load();
      // Offer worker login right after adding a new employee.
      if (!editing && saved && saved.id) setLoginFor(saved);
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
      await api.deleteEmployee(confirmDelete.id);
      setConfirmDelete(null);
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
          <h2>Workforce Registry</h2>
          <p className="page-desc">
            Register operators, technicians and supervisors, track shifts and
            availability, and manage who is assigned to the floor.
          </p>
        </div>
        <button type="button" className="btn-primary" onClick={openAdd}>
          + Add Employee
        </button>
      </div>

      <section className="stat-grid" aria-label="Workforce figures" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
        <StatCard label="Total Employees" value={employees.length} sub="registered" loading={loading} />
        <StatCard label="Active" value={active.length} sub="status ACTIVE" loading={loading} />
        <StatCard
          label="Inactive / Other"
          value={employees.length - active.length}
          sub="all other statuses"
          loading={loading}
        />
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
        <h2>Employee List</h2>
        <EmployeeFilters
          search={search}
          onSearch={setSearch}
          status={statusFilter}
          onStatus={setStatusFilter}
          statuses={statuses}
        />
        {!loading && !loadError && (search.trim() || statusFilter) && visible.length === 0 && employees.length > 0 && (
          <p className="muted" style={{ marginTop: 12 }}>
            No employees match the current search/filter.
          </p>
        )}
        {!loadError && (
          <div style={{ marginTop: 12 }}>
            <EmployeeTable
              employees={visible}
              loading={loading}
              onEdit={openEdit}
              onDelete={setConfirmDelete}
              deletingId={deletingId}
              logins={logins}
              onWorkerLogin={setLoginFor}
            />
          </div>
        )}
      </section>

      {loginFor && (
        <WorkerLoginModal
          employee={loginFor}
          onClose={() => setLoginFor(null)}
          onChanged={() => loadLogins(employees)}
        />
      )}

      {formOpen && (
        <EmployeeForm
          key={editing ? editing.id : 'new'}
          employee={editing}
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

      {confirmDelete && (
        <div className="modal-backdrop" onClick={() => (deletingId ? null : setConfirmDelete(null))}>
          <div
            className="modal modal-narrow"
            role="dialog"
            aria-modal="true"
            aria-label="Confirm deletion"
            onClick={(e) => e.stopPropagation()}
          >
            <h2>Delete Employee</h2>
            <p className="muted">
              Remove <strong>{confirmDelete.name}</strong> ({confirmDelete.role})
              from the registry? This cannot be undone.
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
