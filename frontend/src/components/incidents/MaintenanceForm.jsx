import { useState } from 'react';
import { MAINTENANCE_STATUSES, stripIssuePrefix, toLocalInput } from './incidentWorkflow';

// Maintenance form using ONLY actual Maintenance fields:
//   machine_id (fixed), issue (prefix-locked), description, technician
//   (free text), maintenance_date, resolution, status.
// machineName is display-only; the machine cannot be casually changed.
export default function MaintenanceForm({
  incident,
  machineName,
  record,
  defaultStatus,
  saving,
  apiError,
  onSubmit,
  onClose,
}) {
  const isEdit = !!record;
  const [form, setForm] = useState(() => ({
    issueSuffix: record ? stripIssuePrefix(record.issue, incident.id) : '',
    description: record?.description || '',
    technician: record?.technician || '',
    maintenance_date: toLocalInput(record?.maintenance_date),
    resolution: record?.resolution || '',
    status: record?.status || defaultStatus || 'PENDING',
  }));
  const [errors, setErrors] = useState([]);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const handleSubmit = (e) => {
    e.preventDefault();
    const errs = [];
    if (!form.issueSuffix.trim()) errs.push('Issue description is required');
    if (form.status === 'COMPLETED' && !form.resolution.trim()) {
      errs.push('Resolution is required to complete maintenance');
    }
    let maintenance_date;
    if (form.maintenance_date.trim()) {
      const d = new Date(form.maintenance_date);
      if (Number.isNaN(d.getTime())) errs.push('Maintenance date is not a valid date/time');
      else maintenance_date = d.toISOString();
    } else if (form.status === 'COMPLETED') {
      // Completing stamps "now" when the admin did not supply a date.
      maintenance_date = new Date().toISOString();
    }
    if (errs.length > 0) {
      setErrors(errs);
      return;
    }
    setErrors([]);
    onSubmit({
      issueSuffix: form.issueSuffix.trim(),
      description: form.description.trim() || null,
      technician: form.technician.trim() || null,
      maintenance_date: maintenance_date === undefined ? (isEdit ? null : undefined) : maintenance_date,
      resolution: form.resolution.trim() || null,
      status: form.status,
    });
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={isEdit ? 'Edit maintenance' : 'Create maintenance'}
        onClick={(e) => e.stopPropagation()}
      >
        <h2>{isEdit ? 'Edit Maintenance' : `Create Maintenance — ${machineName}`}</h2>

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
              Issue <b className="required">*</b>{' '}
              <span className="muted">(linked to this incident by prefix)</span>
            </span>
            <input
              value={`Incident ${incident.id}: ${form.issueSuffix}`}
              onChange={(ev) => {
                const prefix = `Incident ${incident.id}: `;
                const v = ev.target.value.startsWith(prefix) ? ev.target.value.slice(prefix.length) : ev.target.value;
                setForm((f) => ({ ...f, issueSuffix: v }));
              }}
              placeholder={`Incident ${incident.id}: <what is wrong>`}
              disabled={saving}
            />
          </label>

          <label className="form-field">
            <span>Description</span>
            <input
              value={form.description}
              onChange={set('description')}
              placeholder="Work details, parts, observations…"
              disabled={saving}
            />
          </label>

          <div className="form-row-2">
            <label className="form-field">
              <span>Technician (free-text assignment)</span>
              <input
                value={form.technician}
                onChange={set('technician')}
                placeholder="e.g. Ahmed Khan"
                disabled={saving}
              />
            </label>
            <label className="form-field">
              <span>Status</span>
              <select value={form.status} onChange={set('status')} disabled={saving}>
                {MAINTENANCE_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="form-row-2">
            <label className="form-field">
              <span>Maintenance date</span>
              <input
                type="datetime-local"
                value={form.maintenance_date}
                onChange={set('maintenance_date')}
                disabled={saving}
              />
            </label>
            <label className="form-field">
              <span>Resolution {form.status === 'COMPLETED' && <b className="required">*</b>}</span>
              <input
                value={form.resolution}
                onChange={set('resolution')}
                placeholder="What was repaired / replaced…"
                disabled={saving}
              />
            </label>
          </div>

          <p className="muted" style={{ marginBottom: 12 }}>
            Technician is a free-text name on the maintenance record — it is not linked to an employee record.
          </p>

          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose} disabled={saving}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Create Maintenance'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
