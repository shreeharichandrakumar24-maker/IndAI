import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { api } from '../../services/api';
import { relTime } from '../../utils/relTime';
import { useVoice } from './useVoice';

// One shared feed of recent FAST voice/text commands. It polls while a
// voice session is connected, shows a lightweight toast when a NEW command
// appears (never re-fires on later polls), and powers the activity strip +
// autonomy switch used by the Jarvis page and the MiniPlayer.

const CmdCtx = createContext(null);

export function useCommandFeed() {
  return useContext(CmdCtx);
}

const POLL_MS = 3000;
const TOAST_MS = 6000;
const MAX_TOASTS = 3;

export function CommandFeedProvider({ children }) {
  const voice = useVoice();
  const session = voice?.session;
  const roomState = voice?.roomState;
  const connected = !!(
    session?.creds && session.phase !== 'idle' && session.phase !== 'error'
    && (roomState?.remoteCount > 0 || session.agentJoined
      || ['live', 'waiting-agent'].includes(session.phase))
  );

  const [commands, setCommands] = useState([]);
  const [autonomy, setAutonomyState] = useState('FAST');
  const [toasts, setToasts] = useState([]);
  const seen = useRef(new Set());
  const primed = useRef(false);
  const timers = useRef([]);

  const refresh = useCallback(async () => {
    let rows;
    try {
      rows = await api.commandsRecent(10);
    } catch {
      return; // backend cold/offline; retried on next poll
    }
    const list = Array.isArray(rows) ? rows : [];
    if (!primed.current) {
      // First successful poll: baseline only, do NOT toast history.
      list.forEach((c) => { if (c.command_id) seen.current.add(c.command_id); });
      primed.current = true;
    } else {
      const fresh = list.filter((c) => c.command_id && !seen.current.has(c.command_id));
      if (fresh.length > 0) {
        fresh.forEach((c) => seen.current.add(c.command_id));
        setToasts((t) => [...fresh, ...t].slice(0, MAX_TOASTS));
        fresh.forEach((c) => {
          timers.current.push(setTimeout(() => {
            setToasts((t) => t.filter((x) => x.command_id !== c.command_id));
          }, TOAST_MS));
        });
      }
      if (seen.current.size > 200) {
        seen.current = new Set(list.map((c) => c.command_id).filter(Boolean));
      }
    }
    setCommands(list);
  }, []);

  useEffect(() => {
    if (!connected) return undefined;
    refresh();
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [connected, refresh]);

  useEffect(() => {
    let cancelled = false;
    api.getAutonomy()
      .then((r) => { if (!cancelled && r?.autonomy) setAutonomyState(r.autonomy); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  useEffect(() => () => { timers.current.forEach(clearTimeout); timers.current = []; }, []);

  const setAutonomy = useCallback(async (mode) => {
    const next = String(mode).toUpperCase() === 'ASK' ? 'ASK' : 'FAST';
    setAutonomyState(next);
    try {
      await api.setAutonomy(next);
    } catch {
      // Put it back if the write failed so the switch never lies.
      try { const r = await api.getAutonomy(); if (r?.autonomy) setAutonomyState(r.autonomy); } catch { /* keep */ }
    }
  }, []);

  const undo = useCallback(async (commandId) => {
    const res = await api.commandUndo(commandId);
    setToasts((t) => t.filter((x) => x.command_id !== commandId));
    await refresh();
    return res;
  }, [refresh]);

  const dismiss = useCallback((commandId) => {
    setToasts((t) => t.filter((x) => x.command_id !== commandId));
  }, []);

  const value = { connected, commands, autonomy, setAutonomy, toasts, undo, dismiss, refresh };
  return <CmdCtx.Provider value={value}>{children}</CmdCtx.Provider>;
}

export function ToastHost() {
  const feed = useCommandFeed();
  if (!feed || feed.toasts.length === 0) return null;
  return (
    <div className="toast-host" role="status" aria-live="polite">
      {feed.toasts.map((c) => (
        <div key={c.command_id} className="toast">
          <div className="toast-main">
            <span className="toast-title">{c.summary || 'Command done'}</span>
            {c.warnings?.length > 0 && (
              <span className="toast-warn">{c.warnings.join('; ')}</span>
            )}
          </div>
          {c.undo_available && (
            <button type="button" className="btn-small" onClick={() => feed.undo(c.command_id)}>
              Undo
            </button>
          )}
          <button
            type="button"
            className="btn-small"
            aria-label="Dismiss"
            onClick={() => feed.dismiss(c.command_id)}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}

export function AutonomySwitch() {
  const feed = useCommandFeed();
  if (!feed) return null;
  return (
    <div className="autonomy-switch" role="group" aria-label="Jarvis autonomy mode">
      <span className="autonomy-label">Autonomy</span>
      <button
        type="button"
        className={feed.autonomy === 'FAST' ? 'btn-small on' : 'btn-small'}
        aria-pressed={feed.autonomy === 'FAST'}
        title="Act immediately and confirm in one sentence"
        onClick={() => feed.setAutonomy('FAST')}
      >
        Fast
      </button>
      <button
        type="button"
        className={feed.autonomy === 'ASK' ? 'btn-small on' : 'btn-small'}
        aria-pressed={feed.autonomy === 'ASK'}
        title="Create a proposal for approval instead of acting"
        onClick={() => feed.setAutonomy('ASK')}
      >
        Ask first
      </button>
    </div>
  );
}

export function ActivityStrip({ compact }) {
  const feed = useCommandFeed();
  const [busy, setBusy] = useState('');
  if (!feed) return null;
  const rows = (feed.commands || []).filter((c) => c.action !== 'undo').slice(0, compact ? 4 : 8);
  return (
    <div className={`activity-strip${compact ? ' compact' : ''}`}>
      <AutonomySwitch />
      {rows.length === 0 ? (
        <p className="muted">No Jarvis commands yet{feed.connected ? '' : ' (connect voice to see activity)'}.</p>
      ) : (
        <ul className="task-list">
          {rows.map((c) => (
            <li key={c.command_id} className="task-row">
              <div className="task-main">
                <span className="cell-strong">{c.summary || c.action}</span>
                <span className="task-meta">
                  {relTime(c.at)}
                  {c.warnings?.length ? ` · ${c.warnings.join('; ')}` : ''}
                </span>
              </div>
              {c.undo_available && (
                <button
                  type="button"
                  className="btn-small"
                  disabled={busy === c.command_id}
                  onClick={async () => {
                    setBusy(c.command_id);
                    try { await feed.undo(c.command_id); } catch { /* 409 shown by next poll */ }
                    finally { setBusy(''); }
                  }}
                >
                  {busy === c.command_id ? '…' : 'Undo'}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
