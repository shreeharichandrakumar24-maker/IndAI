import { useCallback, useEffect, useState } from 'react';
import { api } from '../services/api';

// In-app bell: unread count + dropdown, polls every 30s. Plain-language rows
// written deterministically by the backend (never by the LLM).
export default function NotificationBell({ onNavigate }) {
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async (mark) => {
    try {
      const [count, list] = await Promise.all([
        api.unreadCount().catch(() => ({ unread: 0 })),
        mark === 'open' ? api.notifications({ limit: 10 }) : null,
      ]);
      setUnread(count.unread || 0);
      if (list) setItems(Array.isArray(list) ? list : []);
      setError('');
    } catch (err) {
      if (!String(err.message || '').includes('UNAUTH')) setError('Bell offline');
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load]);

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next) load('open');
  };

  const openItem = async (n) => {
    try { await api.markNotificationRead(n.id); } catch { /* best effort */ }
    setUnread((u) => Math.max(0, u - 1));
    setItems((list) => list.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)));
    setOpen(false);
    if (n.link && onNavigate) onNavigate(n.link);
  };

  const markAll = async () => {
    try {
      await api.markAllNotificationsRead();
      setUnread(0);
      setItems((list) => list.map((x) => ({ ...x, is_read: true })));
    } catch { /* best effort */ }
  };

  return (
    <div style={{ position: 'relative' }} title={error || 'Notifications'}>
      <button type="button" className="btn-small" onClick={toggle} aria-label={`Notifications, ${unread} unread`}>
        🔔 {unread > 0 ? `(${unread})` : ''}
      </button>
      {open && (
        <div className="panel" role="menu" style={{ position: 'absolute', right: 0, top: '110%', width: 340, zIndex: 50, margin: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <b>Notifications</b>
            <button type="button" className="btn-small" onClick={markAll}>Mark all read</button>
          </div>
          {items.length === 0 ? (
            <p className="muted" style={{ marginTop: 8 }}>Nothing new. Breakdowns, at-risk orders and approvals appear here.</p>
          ) : (
            <ul className="task-list" style={{ marginTop: 8 }}>
              {items.map((n) => (
                <li key={n.id} className="task-row" style={n.is_read ? { opacity: 0.65 } : undefined}>
                  <div className="task-main">
                    <span className="cell-strong">{n.title}</span>
                    {n.body && <span className="task-meta">{n.body.slice(0, 120)}</span>}
                  </div>
                  <div className="cell-actions">
                    <button type="button" className="btn-small" onClick={() => openItem(n)}>Open</button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
