import { useEffect, useRef, useState } from 'react';

// KPI card: icon (optional), label, value, sub. Numeric values count up once
// on first mount (short, transform-free); later updates render directly so
// polling pages never re-animate.
function useCountUp(target, loading) {
  const [shown, setShown] = useState(target);
  const done = useRef(false);
  useEffect(() => {
    if (loading || done.current) return undefined;
    const num = Number(target);
    if (!Number.isFinite(num)) {
      done.current = true;
      setShown(target);
      return undefined;
    }
    done.current = true;
    const reduce = typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (reduce || num === 0) {
      setShown(target);
      return undefined;
    }
    const dur = 600;
    const t0 = performance.now();
    let raf = 0;
    const tick = (t) => {
      const k = Math.min(1, (t - t0) / dur);
      const eased = 1 - (1 - k) * (1 - k);
      const val = Math.round(num * eased);
      setShown(Number.isInteger(num) ? val : val);
      if (k < 1) raf = requestAnimationFrame(tick);
      else setShown(target);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [loading, target]);
  return loading ? '—' : shown;
}

export default function StatCard({ label, value, sub, loading, icon }) {
  const display = useCountUp(value, loading);
  return (
    <div className="stat-card">
      <div className="stat-label">{icon && <span aria-hidden="true">{icon} </span>}{label}</div>
      <div className="stat-value">{display}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}
