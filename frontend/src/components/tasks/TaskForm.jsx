import { useState } from 'react';
import { TASK_PRIORITIES, TASK_STATUSES } from './taskWorkflow';

function toLocalInput(value) {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default function TaskForm({ task, employees, machines, orders, saving, apiError, onSubmit, onClose }) {
  const [form, setForm] = useState({
    name: task?.name || '',
    description: task?.description || '',
    required_skill: task?.required_skill || '',
    priority: task?.priority || 'NORMAL',
    status: task?.status || 'PENDING',
    employee_id: task?.employee_id || '',
    machine_id: task?.machine_id || '',
    order_id: task?.order_id || '',
    deadline: toLocalInput(task?.deadline),
    progress: Math.round((task?.progress ?? 0) * 100),
  });
  const [errors, setErrors] = useState([]);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = (e) => {
    e.preventDefault();
    const errs = [];
    if (!form.name.trim()) errs.push('Task name is required');
    if (form.deadline && Number.isNaN(new Date(form.deadline).getTime())) errs.push('Deadline is not a valid date/time');
    const pct = Number(form.progress);
    if (Number.isNaN(pct) || pct < 0 || pct > 100) errs.push('Progress must be 0–100');
    if (errs.length > 0) { setErrors(errs); return; }
    setErrors([]);
    const payload = {
      name: form.name.trim(),
      description: form.description.trim() || null,
      required_skill: form.required_skill.trim() || null,
      priority: form.priority,
      status: form.status,
      employee_id: form.employee_id || null,
      machine_id: form.machine_id || null,
      order_id: form.order_id || null,
      deadline: form.deadline ? new Date(form.deadline).toISOString() : null,
      progress: pct / 100,
    };
    onSubmit(payload);
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={task ? 'Edit task' : 'New task'} onClick={(e) => e.stopPropagation()}>
        <div className="details-head">
          <h2>{task ? 'Edit task' : 'New task'}</h2>
          <button type="button" className="btn-small" onClick={onClose}>Close</button>
        </div>
        {errors.length > 0 && <ul className="form-errors" role="alert">{errors.map((e, i) => <li key={i}>{e}</li>)}</ul>}
        {apiError && <p className="form-errors" role="alert">{apiError}</p>}
        <form onSubmit={submit}>
          <label className="detail-label" htmlFor="task-name">Name *</label>
          <input id="task-name" value={form.name} onChange={set('name')} style={{ width: '100%', marginBottom: 8 }} required />
          <label className="detail-label" htmlFor="task-desc">Description</label>
          <textarea id="task-desc" value={form.description} onChange={set('description')} rows={2} style={{ width: '100%', marginBottom: 8 }} />
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: 140 }}>
              <label className="detail-label">Required skill</label>
              <input value={form.required_skill} onChange={set('required_skill')} style={{ width: '100%' }} placeholder="e.g. CNC operation" />
            </div>
            <div>
              <label className="detail-label">Priority</label>
              <select value={form.priority} onChange={set('priority')}>
                {TASK_PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <div>
              <label className="detail-label">Status</label>
              <select value={form.status} onChange={set('status')}>
                {TASK_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label className="detail-label">Progress %</label>
              <input type="number" min={0} max={100} value={form.progress} onChange={set('progress')} style={{ width: 90 }} />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
            <div style={{ flex: 1, minWidth: 140 }}>
              <label className="detail-label">Assignee</label>
              <select value={form.employee_id} onChange={set('employee_id')} style={{ width: '100%' }}>
                <option value="">— Unassigned —</option>
                {(employees || []).map((e) => <option key={e.id} value={e.id}>{e.name} ({e.role})</option>)}
              </select>
            </div>
            <div style={{ flex: 1, minWidth: 140 }}>
              <label className="detail-label">Machine</label>
              <select value={form.machine_id} onChange={set('machine_id')} style={{ width: '100%' }}>
                <option value="">— None —</option>
                {(machines || []).map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </div>
            <div style={{ flex: 1, minWidth: 140 }}>
              <label className="detail-label">Order</label>
              <select value={form.order_id} onChange={set('order_id')} style={{ width: '100%' }}>
                <option value="">— None —</option>
                {(orders || []).map((o) => <option key={o.id} value={o.id}>{o.order_number}</option>)}
              </select>
            </div>
            <div>
              <label className="detail-label">Deadline</label>
              <input type="datetime-local" value={form.deadline} onChange={set('deadline')} />
            </div>
          </div>
          <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
            <button type="submit" className="btn-primary" disabled={saving}>{saving ? 'Saving…' : task ? 'Save changes' : 'Create task'}</button>
            <button type="button" className="btn-secondary" onClick={onClose} disabled={saving}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );
}
