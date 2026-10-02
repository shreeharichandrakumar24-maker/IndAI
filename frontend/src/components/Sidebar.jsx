import { NAV_ITEMS } from '../config/nav';

export default function Sidebar({ active, onNavigate, role }) {
  const items = NAV_ITEMS.filter((n) => !n.roles || !role || n.roles.includes(role));
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true" />
        <span className="brand-text">
          <strong>IndAI</strong>
          <small>Industrial Admin Platform</small>
        </span>
      </div>
      <nav className="nav">
        {items.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`nav-item${active === item.id ? ' active' : ''}`}
            aria-current={active === item.id ? 'page' : undefined}
            onClick={() => onNavigate(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>
      <div className="sidebar-foot">
        <span>Industry 4.0 Command Center</span>
      </div>
    </aside>
  );
}
