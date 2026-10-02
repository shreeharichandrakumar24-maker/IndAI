import { useState } from 'react';

// Form mirrors backend OrderCreate exactly:
//   order_number*, customer_name?, product?, quantity?, priority?,
//   status?, deadline?, progress?
// Note: OrderUpdate has no order_number, so on edit the number is shown
// read-only and excluded from the PUT payload.
const EMPTY = {
  order_number: '',
  customer_name: '',
  product: '',
  quantity: '',
  priority: 'NORMAL',
  status: 'PENDING',
  deadline: '',
  progress: '',
};

function initialForm(order) {
  if (!order) return { ...EMPTY };
  return {
    order_number: order.order_number || '',
    customer_name: order.customer_name || '',
    product: order.product || '',
    quantity: order.quantity ?? '',
    priority: order.priority || 'NORMAL',
    status: order.status || 'PENDING',
    deadline: order.deadline ? order.deadline.slice(0, 16) : '',
    progress: order.progress ?? '',
  };
}

export default function OrderForm({ order, saving, apiError, onSubmit, onClose }) {
  const isEdit = !!order;
  const [form, setForm] = useState(() => initialForm(order));
  const [errors, setErrors] = useState([]);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const handleSubmit = (e) => {
    e.preventDefault();
    const errs = [];
    if (!isEdit && !form.order_number.trim()) errs.push('Order number is required');
    if (form.quantity !== '' && !Number.isInteger(Number(form.quantity))) {
      errs.push('Quantity must be a whole number');
    }
    if (form.progress !== '' && Number.isNaN(Number(form.progress))) {
      errs.push('Progress must be a number');
    }
    if (form.deadline) {
      const d = new Date(form.deadline);
      if (Number.isNaN(d.getTime())) errs.push('Deadline is not a valid date/time');
    }
    if (errs.length > 0) {
      setErrors(errs);
      return;
    }
    setErrors([]);

    const payload = {};
    if (!isEdit) payload.order_number = form.order_number.trim();
    if (form.customer_name.trim()) payload.customer_name = form.customer_name.trim();
    if (form.product.trim()) payload.product = form.product.trim();
    if (form.quantity !== '') payload.quantity = Number(form.quantity);
    else if (!isEdit) payload.quantity = 0;
    payload.priority = form.priority.trim() || 'NORMAL';
    payload.status = form.status.trim() || 'PENDING';
    if (form.deadline) payload.deadline = new Date(form.deadline).toISOString();
    else if (isEdit) payload.deadline = null;
    if (form.progress !== '') payload.progress = Number(form.progress);
    else if (!isEdit) payload.progress = 0;
    onSubmit(payload);
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={isEdit ? 'Edit order' : 'Create order'}
        onClick={(e) => e.stopPropagation()}
      >
        <h2>{isEdit ? `Edit Order ${order.order_number}` : 'Create Order'}</h2>

        {errors.length > 0 && (
          <ul className="form-errors" role="alert">
            {errors.map((err) => (
              <li key={err}>{err}</li>
            ))}
          </ul>
        )}
        {apiError && (
          <p className="form-errors" role="alert">
            {apiError}
          </p>
        )}

        <form onSubmit={handleSubmit}>
          <label className="form-field">
            <span>
              Order number {isEdit ? '(cannot be changed)' : <b className="required">*</b>}
            </span>
            <input
              value={form.order_number}
              onChange={set('order_number')}
              placeholder="e.g. ORD-2026-001"
              disabled={saving || isEdit}
            />
          </label>

          <div className="form-row-2">
            <label className="form-field">
              <span>Customer</span>
              <input
                value={form.customer_name}
                onChange={set('customer_name')}
                placeholder="e.g. Acme Motors"
                disabled={saving}
              />
            </label>
            <label className="form-field">
              <span>Product</span>
              <input
                value={form.product}
                onChange={set('product')}
                placeholder="e.g. Gear Housing"
                disabled={saving}
              />
            </label>
          </div>

          <div className="form-row-2">
            <label className="form-field">
              <span>Quantity</span>
              <input
                type="number"
                step="1"
                value={form.quantity}
                onChange={set('quantity')}
                placeholder="0"
                disabled={saving}
              />
            </label>
            <label className="form-field">
              <span>Progress (%)</span>
              <input
                type="number"
                step="0.01"
                value={form.progress}
                onChange={set('progress')}
                placeholder="0"
                disabled={saving}
              />
            </label>
          </div>

          <div className="form-row-2">
            <label className="form-field">
              <span>Priority</span>
              <input value={form.priority} onChange={set('priority')} placeholder="NORMAL" disabled={saving} />
            </label>
            <label className="form-field">
              <span>Status</span>
              <input value={form.status} onChange={set('status')} placeholder="PENDING" disabled={saving} />
            </label>
          </div>

          <label className="form-field">
            <span>Deadline</span>
            <input type="datetime-local" value={form.deadline} onChange={set('deadline')} disabled={saving} />
          </label>

          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose} disabled={saving}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? (isEdit ? 'Saving…' : 'Creating…') : isEdit ? 'Save Changes' : 'Create Order'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
