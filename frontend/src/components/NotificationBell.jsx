import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../services/api';
import { relTime } from '../utils/relTime';

// In-app bell: unread count + dropdown, polls every 30s. Plain-language rows
// written deterministically by the backend (never by the LLM).
// Dropdown-only concerns live here: fixed header + scrollable list (never
// taller than the viewport), scroll-to-top on open, outside-click/Esc close,
// and display-only grouping of identical rows. Fetch, counting, mark-read
// and "Open" navigation are unchanged.
function groupItems(items) {
  const groups = [];
  const byKey = new Map();
  for (const n of items || []) {
    const key = `${n.title || ''}|||${n.body || ''}`;
    let g = byKey.get(key);
    if (!g) {
      g = { key, first: n, latest: n, count: 0 };
      byKey.set(key, g);
      groups.push(g);
    }
    g.count += 1;
    if ((n.created_at || '') > (g.latest.created_at || '')) g.latest = n;
  }
  return groups;
}

export default function NotificationBell({ onNavigate }) {
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState('');
  const [moreBelow, setMoreBelow] = useState(false);
  const rootRef = useRef(null);
  const listRef = useRef(null);

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

  // Scroll to top only when the dropdown opens. Poll updates only
  // recompute the bottom fade; scroll position is never touched there.
  useEffect(() => {
    if (!open || !listRef.current) return;
    listRef.current.scrollTop = 0;
  }, [open ]);

  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    setMoreBelow(el.scrollHeight > el.clientHeight + 4);
  }, [open, items.length ]);

  // Outside-click and Esc close (open state only).
  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('pointerdown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open ]);

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

  const groups = groupItems(items);
  const grouped = groups.some((g) => g.count > 1);
  const onListScroll = () => {
    const el = listRef.current;
    if (!el) return;
    setMoreBelow(el.scrollTop + el.clientHeight < el.scrollHeight - 4);
  };

  return (
    <div ref={rootRef} style={{ position: 'relative' }} title={error || (grouped && unread > 0 ? `${unread} notifications, grouped` : 'Notifications')}>
      <button type="button" className="btn-small" onClick={toggle} aria-label={`Notifications, ${unread} unread`} aria-expanded={open} aria-haspopup="menu">
        🔔 {unread > 0 ? `(${unread})` : ''}
      </button>
      {open && (
        <div className="panel notif-panel" role="menu" aria-label="Notifications">
          <div className="notif-head">
            <b>Notifications</b>
            <button type="button" className="btn-small" onClick={markAll}>Mark all read</button>
          </div>
          {groups.length === 0 ? (
            <p className="muted notif-empty">You&apos;re all caught up</p>
          ) : (
            <ul className="task-list notif-list" ref={listRef} tabIndex={0} aria-label="Notifications list" onScroll={onListScroll}>
              {groups.map((g) => (
                <li key={g.first.id} className="task-row" style={g.latest.is_read ? { opacity: 0.65 } : undefined}>
                  <div className="task-main">
                    <span className="cell-strong">
                      {g.first.title}
                      {g.count > 1 && <span className="notif-count" aria-label={`${g.count} similar`}>x{g.count}</span>}
                    </span>
                    {g.first.body && <span className="task-meta">{g.first.body.slice(0, 120)}</span>}
                    <span className="task-meta">{relTime(g.latest.created_at)}</span>
                  </div>
                  <div className="cell-actions">
                    <button type="button" className="btn-small" onClick={() => openItem(g.latest)}>Open</button>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {moreBelow && groups.length > 0 && <div className="notif-fade" aria-hidden="true" />}
        </div>
      )}
    </div>
  );
}
