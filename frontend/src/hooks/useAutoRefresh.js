import { useCallback, useEffect, useRef, useState } from 'react';

// Shared auto-refresh: silent re-fetch every `intervalMs` (default 10 s),
// skipped when the tab is hidden or `paused`. Manual reload anytime.
// Preference persists in localStorage. Pages pass a `quiet`-aware loader so
// auto-refresh never flashes full-page spinners.
export default function useAutoRefresh(onRefresh, { intervalMs = 10000, paused = false } = {}) {
  const [auto, setAutoState] = useState(() => {
    try {
      return localStorage.getItem('indai.autorefresh') !== 'off';
    } catch {
      return true;
    }
  });
  const [lastRefresh, setLastRefresh] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const saved = useRef(onRefresh);
  saved.current = onRefresh;
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  const setAuto = useCallback((v) => {
    setAutoState(v);
    try {
      localStorage.setItem('indai.autorefresh', v ? 'on' : 'off');
    } catch { /* ignore */ }
  }, []);

  const refreshNow = useCallback(async (quiet = true) => {
    setRefreshing(true);
    try {
      await saved.current(quiet);
    } catch { /* page shows its own errors */ }
    finally {
      setRefreshing(false);
      setLastRefresh(new Date());
    }
  }, []);

  useEffect(() => {
    if (!auto) return undefined;
    const timer = setInterval(() => {
      if (!document.hidden && !pausedRef.current) refreshNow(true);
    }, intervalMs);
    return () => clearInterval(timer);
  }, [auto, intervalMs, refreshNow]);

  return { auto, setAuto, lastRefresh, refreshing, refreshNow };
}
