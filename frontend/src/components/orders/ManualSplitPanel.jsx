import { useState } from 'react';
import { api } from '../../services/api';

// Manual task creation using ONLY backend TaskCreate fields:
//   name*, description?, required_skill?, priority?, status?,
//   employee_id?, machine_id?, order_id?, start_time?, deadline?, progress?
// order_id is fixed to the open order. There is deliberately no
// plan/instructions field: the Task model has none, so nothing is faked.
const EMPTY_TASK = {
  name: '',
  description: '',
  required_skill: '',
  priority: 'NORMAL',
  status: 'PENDING',
  employee_id: '',
  machine_id: '',
  start_time: '',
  deadline: '',
};

export default function ManualSplitPanel({ order, employees, machines, onTaskCreated }) {
  const [form, setForm] = useState({ ...EMPTY_TASK });
  const [errors, setErrors] = useState([]);
  const [saving, setSaving] = useState(false);
  const [apiError, setApiError] = useState('');
  const [createdCount, setCreatedCount] = useState(0);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    const errs = [];
    if (!form.name.trim()) errs.push('Task name is required');
    for (const [key, label] of [
      ['start_time', 'Start time'],
      ['deadline', 'Deadline'],
    ]) {
      if (form[key] && Number.isNaN(new Date(form[key]).getTime())) {
        errs.push(`${label} is not a valid date/time`);
      }
    }
    if (errs.length > 0) {
      setErrors(errs);
      return;
    }
    setErrors([]);
    setApiError('');
    setSaving(true);
    try {
      const payload = {
        name: form.name.trim(),
        order_id: order.id,
        priority: form.priority.trim() || 'NORMAL',
        status: form.status.trim() || 'PENDING',
        progress: 0,
      };
      if (form.description.trim()) payload.description = form.description.trim();
      if (form.required_skill.trim()) payload.required_skill = form.required_skill.trim();
      if (form.employee_id) payload.employee_id = form.employee_id;
      if (form.machine_id) payload.machine_id = form.machine_id;
      if (form.start_time) payload.start_time = new Date(form.start_time).toISOString();
      if (form.deadline) payload.deadline = new Date(form.deadline).toISOString();
      await api.createTask(payload);
      setCreatedCount((c) => c + 1);
      setForm({ ...EMPTY_TASK });
      onTaskCreated();
    } catch (err) {
      setApiError(err.message || 'Task creation failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="split-panel">
      <h4>Manual Split — new task for {order.order_number}</h4>
      {createdCount > 0 && (
        <p className="split-note split-note-ok" role="status">
          {createdCount} task{createdCount === 1 ? '' : 's'} created for this order. Add another below.
        </p>
      )}
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
            Task name <b className="required">*</b>
          </span>
          <input value={form.name} onChange={set('name')} placeholder="e.g. Mill gear housing batch" disabled={saving} />
        </label>

        <label className="form-field">
          <span>Description</span>
          <input
            value={form.description}
            onChange={set('description')}
            placeholder="Operation steps, tolerances, …"
            disabled={saving}
          />
        </label>

        <div className="form-row-2">
          <label className="form-field">
            <span>Required skill</span>
            <input
              value={form.required_skill}
              onChange={set('required_skill')}
              placeholder="e.g. CNC milling"
              disabled={saving}
            />
          </label>
          <label className="form-field">
            <span>Priority</span>
            <input value={form.priority} onChange={set('priority')} placeholder="NORMAL" disabled={saving} />
          </label>
        </div>

        <div className="form-row-2">
          <label className="form-field">
            <span>Employee (assignment)</span>
            <select value={form.employee_id} onChange={set('employee_id')} disabled={saving}>
              <option value="">Unassigned</option>
              {employees.map((emp) => (
                <option key={emp.id} value={emp.id}>
                  {emp.name} — {emp.role}
                </option>
              ))}
            </select>
          </label>
          <label className="form-field">
            <span>Machine (assignment)</span>
            <select value={form.machine_id} onChange={set('machine_id')} disabled={saving}>
              <option value="">Unassigned</option>
              {machines.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="form-row-2">
          <label className="form-field">
            <span>Start time</span>
            <input type="datetime-local" value={form.start_time} onChange={set('start_time')} disabled={saving} />
          </label>
          <label className="form-field">
            <span>Deadline</span>
            <input type="datetime-local" value={form.deadline} onChange={set('deadline')} disabled={saving} />
          </label>
        </div>

        <p className="muted" style={{ marginBottom: 12 }}>
          Extension point: the Task model has no plan/instructions field, so detailed work
          instructions are not stored yet. They arrive with the future task-planning layer.
        </p>

        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? 'Creating…' : 'Create Task'}
        </button>
      </form>
    </div>
  );
}
