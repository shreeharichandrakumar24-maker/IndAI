import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../services/api';
import RefreshBar from '../components/RefreshBar';
import useAutoRefresh from '../hooks/useAutoRefresh';
import StatCard from '../components/StatCard';
import OrderFilters from '../components/orders/OrderFilters';
import OrderTable from '../components/orders/OrderTable';
import OrderForm from '../components/orders/OrderForm';
import OrderDetails from '../components/orders/OrderDetails';

const ACTIVE_STATUSES = ['PENDING', 'PLANNED', 'APPROVED', 'IN_PROGRESS', 'IN REVIEW', 'REVIEW'];

export default function Orders({ focusOrderId, presetFilter }) {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  // Voice/typed preset from navigate(page, {filter}).
  useEffect(() => { if (presetFilter) setStatusFilter(presetFilter); }, [presetFilter]);

  // Reference data for assignment dropdowns + FK display in details.
  const [employees, setEmployees] = useState([]);
  const [machines, setMachines] = useState([]);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const [planningOrder, setPlanningOrder] = useState(null);

  const [confirmDelete, setConfirmDelete] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [deleteError, setDeleteError] = useState('');

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    setLoadError('');
    try {
      const [orderData, empData, machData] = await Promise.all([
        api.orders(),
        api.employees().catch(() => []),
        api.machines().catch(() => []),
      ]);
      setOrders(Array.isArray(orderData) ? orderData : []);
      setEmployees(Array.isArray(empData) ? empData : []);
      setMachines(Array.isArray(machData) ? machData : []);
    } catch (err) {
      setLoadError(err.message || 'Failed to load orders');
    } finally {
      if (!quiet) setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Map navigation payload: auto-open planning for the requested order.
  useEffect(() => {
    if (focusOrderId && orders.length > 0) {
      const match = orders.find((o) => o.id === focusOrderId);
      if (match) setPlanningOrder(match);
    }
  }, [focusOrderId, orders]);

  const active = orders.filter((o) => ACTIVE_STATUSES.includes((o.status || '').toUpperCase()));
  const totalQty = orders.reduce((a, o) => a + (o.quantity || 0), 0);
  const statuses = useMemo(
    () => [...new Set(orders.map((o) => o.status).filter(Boolean))].sort(),
    [orders],
  );

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return orders.filter((o) => {
      if (statusFilter && o.status !== statusFilter) return false;
      if (!q) return true;
      return (
        (o.order_number || '').toLowerCase().includes(q) ||
        (o.customer_name || '').toLowerCase().includes(q) ||
        (o.product || '').toLowerCase().includes(q) ||
        String(o.id || '').toLowerCase().includes(q)
      );
    });
  }, [orders, search, statusFilter]);

  const openAdd = () => {
    setEditing(null);
    setFormError('');
    setFormOpen(true);
  };

  const openEdit = (order) => {
    setEditing(order);
    setFormError('');
    setFormOpen(true);
  };

  const handleSubmit = async (payload) => {
    setSaving(true);
    setFormError('');
    try {
      if (editing) {
        await api.updateOrder(editing.id, payload);
      } else {
        await api.createOrder(payload);
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
      await api.deleteOrder(confirmDelete.id);
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
          <h2>Order Management</h2>
          <p className="page-desc">
            Review customer orders, split them into production tasks, and assign
            employees and machines — order → task → assignment → production.
          </p>
        </div>
        <button type="button" className="btn-primary" onClick={openAdd}>
          + Create Order
        </button>
      </div>

      <section className="stat-grid" aria-label="Order figures" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
        <StatCard label="Total Orders" value={orders.length} sub="registered" loading={loading} />
        <StatCard label="Active Orders" value={active.length} sub="pending / in progress" loading={loading} />
        <StatCard label="Total Quantity" value={totalQty} sub="units ordered" loading={loading} />
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
        <h2>Order List</h2>
        <OrderFilters
          search={search}
          onSearch={setSearch}
          status={statusFilter}
          onStatus={setStatusFilter}
          statuses={statuses}
        />
        {!loading && !loadError && (search.trim() || statusFilter) && visible.length === 0 && orders.length > 0 && (
          <p className="muted" style={{ marginTop: 12 }}>
            No orders match the current search/filter.
          </p>
        )}
        {!loadError && (
          <div style={{ marginTop: 12 }}>
            <OrderTable
              orders={visible}
              loading={loading}
              onOpen={setPlanningOrder}
              onEdit={openEdit}
              onDelete={setConfirmDelete}
              deletingId={deletingId}
            />
          </div>
        )}
      </section>

      {formOpen && (
        <OrderForm
          key={editing ? editing.id : 'new'}
          order={editing}
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

      {planningOrder && (
        <OrderDetails
          order={planningOrder}
          employees={employees}
          machines={machines}
          onClose={() => setPlanningOrder(null)}
          onOrderChanged={load}
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
            <h2>Delete Order</h2>
            <p className="muted">
              Delete order{' '}
              <strong>{confirmDelete.order_number}</strong>? Tasks and
              production runs belonging to this order will also be deleted. This cannot be undone.
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
