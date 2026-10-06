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

export default function Topbar({ title, subtitle, crumb, systemStatus, user, onSignOut, onNavigate, onMenu, theme, onToggleTheme, onSwitchFactory, factoryName }) {
  const meta = STATUS_META[systemStatus] || STATUS_META.checking;
  return (
    <header className="topbar">
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', minWidth: 0 }}>
        {onMenu && (
          <button type="button" className="hamburger" onClick={onMenu} aria-label="Open navigation">
            ☰
          </button>
        )}
        <div className="topbar-titles">
          <h1>{title}</h1>
          {crumb ? (
            <p><span className="crumb-section">{crumb}</span><span aria-hidden="true"> · </span>{subtitle}</p>
          ) : (
            subtitle && <p>{subtitle}</p>
          )}
        </div>
      </div>
      {factoryName && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
          <span className="muted" style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 220 }} title={factoryName}>
            🏭 {factoryName}
          </span>
          {onSwitchFactory && (
            <button type="button" className="btn-small" onClick={onSwitchFactory} title="Switch company / factory">
              Switch Company
            </button>
          )}
        </div>
      )}
      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        {onToggleTheme && (
          <button
            type="button"
            className="theme-toggle"
            onClick={onToggleTheme}
            aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
            title={theme === 'dark' ? 'Light theme' : 'Dark theme'}
          >
            {theme === 'dark' ? '☀' : '◐'}
          </button>
        )}
        {user && user.role !== 'WORKER' && <NotificationBell onNavigate={onNavigate} />}
        {user && (
          <span className="muted topbar-user" title={user.email || ''}>
            <span className="user-name">{user.name || user.email} </span><StatusBadge tone={toneForRole(user.role)}>{user.role}</StatusBadge>{' '}
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
