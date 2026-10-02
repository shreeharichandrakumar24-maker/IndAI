import StatusBadge from '../StatusBadge';
import { toneForOrderStatus, formatDateTime } from '../../utils/orders';

export default function OrderTable({ orders, loading, onOpen, onEdit, onDelete, deletingId }) {
  if (loading) return <p className="muted">Loading orders…</p>;
  if (orders.length === 0) {
    return (
      <div className="empty-state">
        <p className="empty-title">No orders registered yet.</p>
        <p className="muted">Create your first order to start the order → task → production workflow.</p>
      </div>
    );
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Order No.</th>
            <th>Customer</th>
            <th>Product</th>
            <th>Qty</th>
            <th>Priority</th>
            <th>Status</th>
            <th>Deadline</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {orders.map((o) => (
            <tr key={o.id}>
              <td className="cell-strong">{o.order_number}</td>
              <td>{o.customer_name || '—'}</td>
              <td>{o.product || '—'}</td>
              <td>{o.quantity ?? '—'}</td>
              <td>{o.priority || '—'}</td>
              <td>
                <StatusBadge tone={toneForOrderStatus(o.status)}>{o.status || 'PENDING'}</StatusBadge>
              </td>
              <td>{formatDateTime(o.deadline)}</td>
              <td className="cell-actions">
                <button type="button" className="btn-small" onClick={() => onOpen(o)}>
                  Plan
                </button>
                <button type="button" className="btn-small" onClick={() => onEdit(o)}>
                  Edit
                </button>
                <button
                  type="button"
                  className="btn-small btn-danger"
                  disabled={deletingId === o.id}
                  onClick={() => onDelete(o)}
                >
                  {deletingId === o.id ? 'Deleting…' : 'Delete'}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
