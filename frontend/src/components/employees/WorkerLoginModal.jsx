import { useEffect, useState } from 'react';
import { api } from '../../services/api';
import StatusBadge from '../StatusBadge';

// Worker-login manager for one employee: shows code/email/username,
// creates a login (email editable) or resets the password. The generated
// password is shown ONCE in a copyable box — never stored client-side
// beyond this modal, never logged.
export default function WorkerLoginModal({ employee, onClose, onChanged }) {
  const [info, setInfo] = useState(null);
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [tempCreds, setTempCreds] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setInfo(null);
    setTempCreds(null);
    setError('');
    api.workerLoginInfo(employee.id)
      .then((d) => { if (!cancelled) { setInfo(d); setEmail(d.email || ''); } })
      .catch((err) => { if (!cancelled) setError(err.message || 'Failed to load login'); });
    return () => { cancelled = true; };
  }, [employee.id]);

  const create = async () => {
    setBusy('create');
    setError('');
    try {
      const res = await api.createWorkerLogin(employee.id, email.trim() || undefined);
      setTempCreds(res);
      setInfo({ has_login: true, employee_code: res.employee_code, email: res.email, username: res.username });
      if (onChanged) onChanged();
    } catch (err) {
      setError(err.message || 'Create failed');
    } finally {
      setBusy('');
    }
  };

  const reset = async () => {
    setBusy('reset');
    setError('');
    try {
      const res = await api.resetWorkerLogin(employee.id);
      setTempCreds(res);
      if (onChanged) onChanged();
    } catch (err) {
      setError(err.message || 'Reset failed');
    } finally {
      setBusy('');
    }
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(tempCreds.temp_password);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={`Worker login for ${employee.name}`} onClick={(e) => e.stopPropagation()}>
        <div className="details-head">
          <h2>Worker login <span className="muted">— {employee.name}</span></h2>
          <button type="button" className="btn-small" onClick={onClose}>Close</button>
        </div>
        {error && <p className="form-errors" role="alert">{error}</p>}
        {!info ? <p className="muted">Loading…</p> : (
          <>
            <p>
              {info.has_login ? <StatusBadge tone="ok">Has login</StatusBadge> : <StatusBadge tone="neutral">No login</StatusBadge>}
            </p>
            {info.has_login && (
              <>
                <p className="muted">Code: <span className="cell-mono">{info.employee_code || '—'}</span></p>
                <p className="muted">Email: {info.email || '—'}</p>
                <p className="muted">Username: <span className="cell-mono">{info.username || '—'}</span></p>
              </>
            )}
            {!info.has_login && (
              <div style={{ marginTop: 8 }}>
                <label className="detail-label" htmlFor="wl-email">Email for the new login</label>
                <input id="wl-email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@indai-factory.example" style={{ width: '100%' }} />
                <div style={{ marginTop: 8 }}>
                  <button type="button" className="btn-primary" disabled={busy === 'create'} onClick={create}>
                    {busy === 'create' ? 'Creating…' : 'Create login'}
                  </button>
                </div>
              </div>
            )}
            {info.has_login && (
              <div style={{ marginTop: 8 }}>
                <button type="button" className="btn-secondary" disabled={busy === 'reset'} onClick={reset}>
                  {busy === 'reset' ? 'Resetting…' : 'Reset password'}
                </button>
              </div>
            )}
            {tempCreds && (
              <div className="panel" role="status" style={{ marginTop: 12 }}>
                <p><b>Temporary password — shown once. Copy it now.</b></p>
                <p className="cell-mono" style={{ fontSize: '1.1rem' }}>{tempCreds.temp_password}</p>
                <p className="muted">{tempCreds.username} · {tempCreds.employee_code} · {tempCreds.email}</p>
                <button type="button" className="btn-small" onClick={copy}>{copied ? 'Copied ✓' : 'Copy password'}</button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
