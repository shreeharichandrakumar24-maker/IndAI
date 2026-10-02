// Reload bar: manual Reload button + Auto (10 s) toggle + last-updated label.
// Same look on every tab (existing design language: btn-small, muted).
export default function RefreshBar({ auto, onAuto, onReload, refreshing, lastRefresh }) {
  const age = !lastRefresh
    ? 'not yet'
    : (() => {
      const s = Math.max(0, Math.round((Date.now() - lastRefresh.getTime()) / 1000));
      if (s < 5) return 'just now';
      if (s < 60) return `${s}s ago`;
      return `${Math.floor(s / 60)}m ago`;
    })();
  return (
    <div className="refresh-bar" role="status" aria-label="Data freshness">
      <button type="button" className="btn-small" onClick={() => onReload(false)} disabled={refreshing}>
        {refreshing ? '↻ Reloading…' : '↻ Reload'}
      </button>
      <label className="refresh-auto">
        <input type="checkbox" checked={auto} onChange={(e) => onAuto(e.target.checked)} />
        Auto (10s)
      </label>
      <span className="muted">Updated {age}</span>
    </div>
  );
}
