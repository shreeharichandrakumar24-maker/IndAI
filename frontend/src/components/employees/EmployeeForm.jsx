import { useState } from 'react';

// Form mirrors backend EmployeeCreate exactly:
//   name*, role*, skills?, certifications?, shift?, status?, availability?
// skills/certifications are Dict[str, Any] in the API, so the inputs accept
// a JSON object and validate it before submit. No invented fields.
const EMPTY = {
  name: '',
  role: '',
  skillsText: '',
  certificationsText: '',
  shift: '',
  status: 'ACTIVE',
  availability: 'AVAILABLE',
};

function toJsonText(value) {
  if (!value || typeof value !== 'object' || Object.keys(value).length === 0) return '';
  try {
    return JSON.stringify(value);
  } catch {
    return '';
  }
}

function parseDictField(text, label, errors) {
  const t = (text || '').trim();
  if (!t) return undefined;
  try {
    const parsed = JSON.parse(t);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      errors.push(`${label} must be a JSON object, e.g. {"welding": "expert"}`);
      return undefined;
    }
    return parsed;
  } catch {
    errors.push(`${label} is not valid JSON`);
    return undefined;
  }
}

function initialForm(employee) {
  if (!employee) return { ...EMPTY };
  return {
    name: employee.name || '',
    role: employee.role || '',
    skillsText: toJsonText(employee.skills),
    certificationsText: toJsonText(employee.certifications),
    shift: employee.shift || '',
    status: employee.status || 'ACTIVE',
    availability: employee.availability || 'AVAILABLE',
  };
}

export default function EmployeeForm({ employee, saving, apiError, onSubmit, onClose }) {
  const isEdit = !!employee;
  // Initialized once per mount; the parent remounts the form per employee
  // via key, so no sync effect is needed.
  const [form, setForm] = useState(() => initialForm(employee));
  const [errors, setErrors] = useState([]);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const handleSubmit = (e) => {
    e.preventDefault();
    const errs = [];
    if (!form.name.trim()) errs.push('Name is required');
    if (!form.role.trim()) errs.push('Role is required');
    const skills = parseDictField(form.skillsText, 'Skills', errs);
    const certifications = parseDictField(form.certificationsText, 'Certifications', errs);
    if (errs.length > 0) {
      setErrors(errs);
      return;
    }
    setErrors([]);
    const payload = {
      name: form.name.trim(),
      role: form.role.trim(),
      shift: form.shift.trim() || null,
      status: form.status.trim() || 'ACTIVE',
      availability: form.availability.trim() || 'AVAILABLE',
    };
    // Omit empty optionals on create; send explicit nulls cleared on edit.
    if (skills !== undefined) payload.skills = skills;
    else if (isEdit) payload.skills = null;
    if (certifications !== undefined) payload.certifications = certifications;
    else if (isEdit) payload.certifications = null;
    onSubmit(payload);
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={isEdit ? 'Edit employee' : 'Add employee'}
        onClick={(e) => e.stopPropagation()}
      >
        <h2>{isEdit ? 'Edit Employee' : 'Add Employee'}</h2>

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
            <input value={form.name} onChange={set('name')} placeholder="e.g. Ahmed Khan" disabled={saving} />
          </label>

          <label className="form-field">
            <span>
              Role <b className="required">*</b>
            </span>
            <input value={form.role} onChange={set('role')} placeholder="e.g. CNC Operator" disabled={saving} />
          </label>

          <div className="form-row">
            <label className="form-field">
              <span>Shift</span>
              <input value={form.shift} onChange={set('shift')} placeholder="e.g. Morning" disabled={saving} />
            </label>
            <label className="form-field">
              <span>Status</span>
              <input value={form.status} onChange={set('status')} placeholder="ACTIVE" disabled={saving} />
            </label>
            <label className="form-field">
              <span>Availability</span>
              <input
                value={form.availability}
                onChange={set('availability')}
                placeholder="AVAILABLE"
                disabled={saving}
              />
            </label>
          </div>

          <label className="form-field">
            <span>Skills (JSON object)</span>
            <input
              value={form.skillsText}
              onChange={set('skillsText')}
              placeholder='{"welding": "expert", "cnc": "level-2"}'
              disabled={saving}
              spellCheck={false}
            />
          </label>

          <label className="form-field">
            <span>Certifications (JSON object)</span>
            <input
              value={form.certificationsText}
              onChange={set('certificationsText')}
              placeholder='{"safety": "2026-01-15"}'
              disabled={saving}
              spellCheck={false}
            />
          </label>

          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose} disabled={saving}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? (isEdit ? 'Saving…' : 'Adding…') : isEdit ? 'Save Changes' : 'Add Employee'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
