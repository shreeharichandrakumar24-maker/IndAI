import { useState } from 'react';
import { toLocalInput } from './productionTone';

// Form mirrors backend ProductionRunCreate / ProductionRunUpdate exactly:
//   order_id?, task_id?, machine_id?, quantity_target?, quantity_completed?,
//   status?, start_time?, estimated_completion?
// No invented fields. The schema has no end_time and no employee field, so
// neither is offered. FK selectors show human-readable labels but submit IDs.
const EMPTY = {
  order_id: '',
  task_id: '',
  machine_id: '',
  quantity_target: '0',
  quantity_completed: '0',
  status: 'PLANNED',
  start_time: '',
  estimated_completion: '',
};

function initialForm(run) {
  if (!run) return { ...EMPTY };
  return {
    order_id: run.order_id || '',
    task_id: run.task_id || '',
    machine_id: run.machine_id || '',
    quantity_target: run.quantity_target ?? '0',
    quantity_completed: run.quantity_completed ?? '0',
    status: run.status || 'PLANNED',
    start_time: toLocalInput(run.start_time),
    estimated_completion: toLocalInput(run.estimated_completion),
  };
}

function parseIntField(text, label, errors) {
  const t = String(text ?? '').trim();
  if (!t) return 0;
  const n = Number(t);
  if (!Number.isInteger(n) || n < 0) {
    errors.push(`${label} must be a non-negative whole number`);
    return null;
  }
  return n;
}

function parseDateField(text, label, errors) {
  const t = (text || '').trim();
  if (!t) return undefined;
  const d = new Date(t);
  if (Number.isNaN(d.getTime())) {
    errors.push(`${label} is not a valid date/time`);
    return null;
  }
  return d.toISOString();
}

export default function ProductionForm({ run, orders, tasks, machines, saving, apiError, onSubmit, onClose }) {
  const isEdit = !!run;
  // Initialized once per mount; the parent remounts the form per run
  // via key, so no sync effect is needed.
  const [form, setForm] = useState(() => initialForm(run));
  const [errors, setErrors] = useState([]);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  // Order -> Task hierarchy: the task list follows the selected order, and
  // picking a task reveals its order (derived the same way the backend
  // files a run under its task). The current selection always stays visible.
  const orderNumberById = Object.fromEntries(orders.map((o) => [o.id, o.order_number || String(o.id).slice(0, 8)]));
  const visibleTasks = form.order_id
    ? tasks.filter((t) => !t.order_id || t.order_id === form.order_id || t.id === form.task_id)
    : tasks;

  const handleTaskChange = (e) => {
    const id = e.target.value;
    const picked = tasks.find((t) => String(t.id) === String(id));
    setForm((f) => ({
      ...f,
      task_id: id,
      order_id: picked && picked.order_id ? picked.order_id : f.order_id,
    }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const errs = [];
    const quantity_target = parseIntField(form.quantity_target, 'Quantity target', errs);
    const quantity_completed = parseIntField(form.quantity_completed, 'Quantity completed', errs);
    const start_time = parseDateField(form.start_time, 'Start time', errs);
    const estimated_completion = parseDateField(form.estimated_completion, 'Estimated completion', errs);
    if (quantity_target === null || quantity_completed === null || start_time === null || estimated_completion === null) {
      setErrors(errs);
      return;
    }
    if (errs.length > 0) {
      setErrors(errs);
      return;
    }
    setErrors([]);
    const fk = (v) => {
      // Omit empty FKs on create; send explicit nulls on edit so a cleared
      // selector actually unlinks instead of leaving the old value stale.
      if (!v) return isEdit ? null : undefined;
      return v;
    };
    const payload = {
      quantity_target,
      quantity_completed,
      status: form.status.trim() || 'PLANNED',
    };
    const order_id = fk(form.order_id);
    const task_id = fk(form.task_id);
    const machine_id = fk(form.machine_id);
    if (order_id !== undefined) payload.order_id = order_id;
    if (task_id !== undefined) payload.task_id = task_id;
    if (machine_id !== undefined) payload.machine_id = machine_id;
    // Datetimes: omit when empty on create, explicit null on edit.
    if (start_time !== undefined) payload.start_time = start_time;
    else if (isEdit) payload.start_time = null;
    if (estimated_completion !== undefined) payload.estimated_completion = estimated_completion;
    else if (isEdit) payload.estimated_completion = null;
    onSubmit(payload);
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={isEdit ? 'Edit production run' : 'Start production run'}
        onClick={(e) => e.stopPropagation()}
      >
        <h2>{isEdit ? 'Edit Production Run' : 'Start Production Run'}</h2>

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
          <div className="form-row-2">
            <label className="form-field">
              <span>Order</span>
              <select value={form.order_id} onChange={set('order_id')} disabled={saving}>
                <option value="">Unlinked</option>
                {orders.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.order_number || String(o.id).slice(0, 8)}
                    {o.product ? ` — ${o.product}` : ''}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-field">
              <span>Task</span>
              <select value={form.task_id} onChange={handleTaskChange} disabled={saving}>
                <option value="">Unlinked</option>
                {visibleTasks.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                    {t.order_id && orderNumberById[t.order_id] ? ` — ${orderNumberById[t.order_id]}` : ''}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="form-row-2">
            <label className="form-field">
              <span>Machine</span>
              <select value={form.machine_id} onChange={set('machine_id')} disabled={saving}>
                <option value="">Unlinked</option>
                {machines.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="form-field">
              <span>Status</span>
              <input
                value={form.status}
                onChange={set('status')}
                placeholder="PLANNED"
                disabled={saving}
              />
            </label>
          </div>

          <div className="form-row-2">
            <label className="form-field">
              <span>Quantity target</span>
              <input
                type="number"
                min="0"
                step="1"
                value={form.quantity_target}
                onChange={set('quantity_target')}
                disabled={saving}
              />
            </label>
            <label className="form-field">
              <span>Quantity completed</span>
              <input
                type="number"
                min="0"
                step="1"
                value={form.quantity_completed}
                onChange={set('quantity_completed')}
                disabled={saving}
              />
            </label>
          </div>

          <div className="form-row-2">
            <label className="form-field">
              <span>Start time</span>
              <input type="datetime-local" value={form.start_time} onChange={set('start_time')} disabled={saving} />
            </label>
            <label className="form-field">
              <span>Estimated completion</span>
              <input
                type="datetime-local"
                value={form.estimated_completion}
                onChange={set('estimated_completion')}
                disabled={saving}
              />
            </label>
          </div>

          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose} disabled={saving}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? (isEdit ? 'Saving…' : 'Starting…') : isEdit ? 'Save Changes' : 'Start Run'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
