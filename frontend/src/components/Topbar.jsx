import StatusBadge from './StatusBadge';
import NotificationBell from './NotificationBell';

const STATUS_META = {
  online: { dot: 'ok', label: 'SYSTEM ONLINE' },
  degraded: { dot: 'warn', label: 'API UP · DB UNREACHABLE' },
  offline: { dot: 'bad', label: 'BACKEND OFFLINE' },
  checking: { dot: 'warn', label: 'CHECKING…' },
};

function toneForRole(role) {
  if (role === 'MANAGER') return 'warn';
  if (role === 'OPERATOR') return 'info';
  return 'neutral';
}

export default function Topbar({ title, subtitle, systemStatus, user, onSignOut, onNavigate }) {
  const meta = STATUS_META[systemStatus] || STATUS_META.checking;
  return (
    <header className="topbar">
      <div className="topbar-titles">
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        {user && user.role !== 'WORKER' && <NotificationBell onNavigate={onNavigate} />}
        {user && (
          <span className="muted" title={user.email || ''}>
            {user.name || user.email} <StatusBadge tone={toneForRole(user.role)}>{user.role}</StatusBadge>{' '}
            {onSignOut ? (
              <button type="button" className="btn-small" onClick={onSignOut}>Sign out</button>
            ) : (
              <StatusBadge tone="warn">DEV MODE</StatusBadge>
            )}
          </span>
        )}
        <div className="sys-status" title="FastAPI + database health">
          <span className={`sys-dot ${meta.dot}`} aria-hidden="true" />
          <span className="sys-label">{meta.label}</span>
        </div>
      </div>
    </header>
  );
}
