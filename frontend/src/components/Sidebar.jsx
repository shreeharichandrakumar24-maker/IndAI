import { useEffect, useRef } from 'react';
import { NAV_ITEMS, NAV_SECTIONS } from '../config/nav';

// Grouped sections shorten the rail. SAME nav ids + labels (nav.js
// untouched) so state-based routing in App.jsx is unchanged.
const SECTIONS = NAV_SECTIONS;

// Text glyphs keep the collapsed rail icon-only without new dependencies.
const GLYPHS = {
  dashboard: '▦', map: '◈', profile: '⚙', import: '⤴', employees: '⛉',
  tasks: '☑', machines: '⚒', orders: '▤', production: '⚗', iot: '◉',
  simulator: '▶', incidents: '⚠', memory: '✎', reports: '▥', plans: '✦',
  simulate: '◍', users: '⛨', ai: '✣', jarvis: '◍',
};
const JARVIS_GLYPH = '✦';

export default function Sidebar({ active, onNavigate, role, collapsed, onToggleCollapse, drawerOpen, onCloseDrawer }) {
  const navRef = useRef(null);
  const itemRefs = useRef({});

  // Keep the active item visible when the route changes (voice ui.command
  // navigation included). Scroll position is otherwise preserved because the
  // nav region never remounts when switching pages.
  useEffect(() => {
    const el = itemRefs.current[active];
    if (el && typeof el.scrollIntoView === 'function') {
      try {
        el.scrollIntoView({ block: 'nearest' });
      } catch { /* older browsers: no-op */ }
    }
  }, [active]);

  const byId = {};
  for (const n of NAV_ITEMS) byId[n.id] = n;
  const visible = (id) => {
    const n = byId[id];
    return n && (!n.roles || !role || n.roles.includes(role));
  };
  const jarvisVisible = visible('jarvis');

  const renderItem = (id) => {
    const item = byId[id];
    if (!item || !visible(id)) return null;
    const isActive = active === id;
    return (
      <button
        key={item.id}
        ref={(el) => { if (el) itemRefs.current[item.id] = el; }}
        type="button"
        title={collapsed ? item.label : undefined}
        aria-label={collapsed ? item.label : undefined}
        className={`nav-item${isActive ? ' active' : ''}`}
        aria-current={isActive ? 'page' : undefined}
        onClick={() => onNavigate(item.id)}
      >
        <span className="nav-glyph" aria-hidden="true">{GLYPHS[item.id] || '•'}</span>
        <span className="nav-label">{item.label}</span>
      </button>
    );
  };

  return (
    <>
      <div
        className={`drawer-scrim${drawerOpen ? ' open' : ''}`}
        aria-hidden="true"
        onClick={onCloseDrawer}
      />
      <aside
        className={`sidebar${collapsed ? ' rail' : ''}${drawerOpen ? ' drawer-open' : ''}`}
        aria-label="Primary navigation"
      >
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <span className="brand-text">
            <strong>IndAI</strong>
            <small>Industrial Admin Platform</small>
          </span>
        </div>
        <nav className="nav" ref={navRef} aria-label="Sections">
          {SECTIONS.map((s) => {
            const ids = s.ids.filter(visible);
            if (ids.length === 0) return null;
            return (
              <div key={s.label} className="nav-section">
                <div className="nav-section-label" aria-hidden="true">{s.label}</div>
                {ids.map(renderItem)}
              </div>
            );
          })}
        </nav>
        <div className="sidebar-foot">
          {jarvisVisible && (
            <button
              type="button"
              className={`nav-item jarvis-quick${active === 'jarvis' ? ' active' : ''}`}
              aria-current={active === 'jarvis' ? 'page' : undefined}
              title={collapsed ? 'Jarvis' : undefined}
              onClick={() => onNavigate('jarvis')}
            >
              <span className="nav-glyph jarvis-orb-dot" aria-hidden="true">{JARVIS_GLYPH}</span>
              <span className="nav-label">Jarvis</span>
            </button>
          )}
          <button
            type="button"
            className="rail-toggle"
            onClick={onToggleCollapse}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            title={collapsed ? 'Expand' : 'Collapse'}
          >
            {collapsed ? '»' : '« Collapse'}
          </button>
          <span className="foot-note">Industry 4.0 Command Center</span>
        </div>
      </aside>
    </>
  );
}
