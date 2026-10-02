import { useState } from 'react';

// Form mirrors backend MachineCreate / MachineUpdate exactly:
//   name*, machine_type?, location?, status?, health_status?
// No invented fields. Backend defaults: status OPERATIONAL, health GOOD.
const EMPTY = {
  name: '',
  machine_type: '',
  location: '',
  status: 'OPERATIONAL',
  health_status: 'GOOD',
};

function initialForm(machine) {
  if (!machine) return { ...EMPTY };
  return {
    name: machine.name || '',
    machine_type: machine.machine_type || '',
    location: machine.location || '',
    status: machine.status || 'OPERATIONAL',
    health_status: machine.health_status || 'GOOD',
  };
}

export default function MachineForm({ machine, saving, apiError, onSubmit, onClose }) {
  const isEdit = !!machine;
  // Initialized once per mount; the parent remounts the form per machine
  // via key, so no sync effect is needed.
  const [form, setForm] = useState(() => initialForm(machine));
  const [errors, setErrors] = useState([]);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const handleSubmit = (e) => {
    e.preventDefault();
    const errs = [];
    if (!form.name.trim()) errs.push('Name is required');
    if (errs.length > 0) {
      setErrors(errs);
      return;
    }
    setErrors([]);
    const opt = (v) => {
      const t = (v || '').trim();
      // Omit empty optionals on create; send explicit nulls on edit so a
      // cleared field is actually cleared instead of left stale.
      if (!t) return isEdit ? null : undefined;
      return t;
    };
    const payload = { name: form.name.trim() };
    const machine_type = opt(form.machine_type);
    const location = opt(form.location);
    const status = opt(form.status) ?? (isEdit ? null : 'OPERATIONAL');
    const health_status = opt(form.health_status) ?? (isEdit ? null : 'GOOD');
    if (machine_type !== undefined) payload.machine_type = machine_type;
    if (location !== undefined) payload.location = location;
    if (status !== undefined) payload.status = status;
    if (health_status !== undefined) payload.health_status = health_status;
    onSubmit(payload);
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={isEdit ? 'Edit machine' : 'Add machine'}
        onClick={(e) => e.stopPropagation()}
      >
        <h2>{isEdit ? 'Edit Machine' : 'Add Machine'}</h2>

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
              Name <b className="required">*</b>
            </span>
            <input
              value={form.name}
              onChange={set('name')}
              placeholder="e.g. M-009 CNC Milling Machine"
              disabled={saving}
            />
          </label>

          <div className="form-row-2">
            <label className="form-field">
              <span>Machine Type</span>
              <input
                value={form.machine_type}
                onChange={set('machine_type')}
                placeholder="e.g. CNC"
                disabled={saving}
              />
            </label>
            <label className="form-field">
              <span>Location</span>
              <input
                value={form.location}
                onChange={set('location')}
                placeholder="e.g. Bay A - North"
                disabled={saving}
              />
            </label>
          </div>

          <div className="form-row-2">
            <label className="form-field">
              <span>Status</span>
              <input
                value={form.status}
                onChange={set('status')}
                placeholder="OPERATIONAL"
                disabled={saving}
              />
            </label>
            <label className="form-field">
              <span>Health Status</span>
              <input
                value={form.health_status}
                onChange={set('health_status')}
                placeholder="GOOD"
                disabled={saving}
              />
            </label>
          </div>

          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose} disabled={saving}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? (isEdit ? 'Saving…' : 'Adding…') : isEdit ? 'Save Changes' : 'Add Machine'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
