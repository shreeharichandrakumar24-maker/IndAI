import { useCallback, useEffect, useState } from 'react';
import { api } from '../services/api';
import RefreshBar from '../components/RefreshBar';
import useAutoRefresh from '../hooks/useAutoRefresh';
import StatCard from '../components/StatCard';
import StatusBadge from '../components/StatusBadge';
import { formatDateTime } from '../components/incidents/incidentWorkflow';

const ROLES = ['MANAGER', 'OPERATOR', 'WORKER'];

// Manager-only: who can sign in, what role they hold, activate/deactivate.
// Accounts themselves are created in the Supabase dashboard (Authentication).
export default function Users({ me }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    setError('');
    try {
      const data = await api.users();
      setRows(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message || 'Failed to load users');
    } finally {
      if (!quiet) setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const changeRole = async (u, role) => {
    setBusy(u.id + role);
    setError('');
    try {
      await api.setUserRole(u.id, role);
      await load();
    } catch (err) {
      setError(err.message || 'Role change failed');
    } finally {
      setBusy('');
    }
  };

  const toggleActive = async (u) => {
    setBusy(u.id + 'active');
    setError('');
    try {
      await api.updateUser(u.id, { active: !u.active });
      await load();
    } catch (err) {
      setError(err.message || 'Update failed');
    } finally {
      setBusy('');
    }
  };

  const managers = rows.filter((r) => r.role === 'MANAGER' && r.active).length;

  const refresher = useAutoRefresh(load);

  return (
    <div className="page">
      <RefreshBar auto={refresher.auto} onAuto={refresher.setAuto} onReload={refresher.refreshNow} refreshing={refresher.refreshing} lastRefresh={refresher.lastRefresh} />
      <div className="page-head">
        <div>
          <h2>Users & roles</h2>
          <p className="page-desc">Signed in as {me?.email}. New accounts are created in Supabase (Authentication); roles are assigned here. The last active manager cannot be demoted.</p>
        </div>
      </div>

      <section className="stat-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
        <StatCard label="Users" value={rows.length} sub="can sign in" loading={loading} />
        <StatCard label="Managers" value={managers} sub="full access" loading={loading} />
        <StatCard label="Deactivated" value={rows.filter((r) => !r.active).length} sub="blocked" loading={loading} />
      </section>

      {error && <div className="alert-banner" role="alert">{error} <button type="button" className="btn-small" onClick={load}>Retry</button></div>}

      <section className="panel">
        <h2>All users</h2>
        {loading ? <p className="muted">Loading…</p> : (
          <table className="data-table">
            <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Joined</th><th>Actions</th></tr></thead>
            <tbody>
              {rows.map((u) => {
                const lastManager = u.role === 'MANAGER' && u.active && managers <= 1;
                return (
                  <tr key={u.id} style={!u.active ? { opacity: 0.6 } : undefined}>
                    <td className="cell-strong">{u.name || '—'}</td>
                    <td className="muted">{u.email || '—'}</td>
                    <td>
                      <select value={u.role} disabled={!!busy || lastManager} onChange={(e) => changeRole(u, e.target.value)} title={lastManager ? 'Last active manager cannot be demoted' : 'Change role'}>
                        {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                      </select>
                    </td>
                    <td><StatusBadge tone={u.active ? 'ok' : 'neutral'}>{u.active ? 'ACTIVE' : 'OFF'}</StatusBadge></td>
                    <td className="cell-mono muted">{formatDateTime(u.created_at)}</td>
                    <td>
                      {u.id !== me?.id && (
                        <button type="button" className="btn-small" disabled={!!busy} onClick={() => toggleActive(u)}>
                          {u.active ? 'Deactivate' : 'Activate'}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
