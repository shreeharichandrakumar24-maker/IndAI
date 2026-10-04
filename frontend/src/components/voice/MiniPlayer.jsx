import { useEffect, useState } from 'react';
import { api } from '../../services/api';
import StatusBadge from '../StatusBadge';
import EmployeeCode from '../EmployeeCode';
import { useVoice, voiceStateLabel } from './useVoice';
import { ActivityStrip } from './CommandFeed';

// Fixed dock positions only (no dragging): bottom-right (default) or
// bottom-center, positioned with CSS. The old free-form position value is
// deleted on load so nobody keeps a stale mid-page spot.
const STALE_POS_KEY = 'indai.miniplayer.pos';
const DOCK_KEY = 'indai.miniplayer.dock';

// Pending proposals mini-list (polls while mounted). Shared by the mini
// player card and the full Jarvis page. Same endpoint, no new API.
export function ProposalMiniList() {
  const [items, setItems] = useState([]);
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await api.proposalsPending();
        if (!cancelled) setItems(Array.isArray(data) ? data : []);
      } catch { /* ignore; retried on next poll */ }
    };
    load();
    const t = setInterval(load, 5000);
    return () => { cancelled = true; clearInterval(t); };
  }, []);
  const [busy, setBusy] = useState('');
  const decide = async (id, decision) => {
    setBusy(id + decision);
    try {
      await api.decideRecommendation(id, decision, '');
      setItems((l) => l.filter((x) => x.id !== id));
    } catch { /* error shown inline below */ }
    finally {
      setBusy('');
    }
  };
  if (items.length === 0) return <p className="muted">No pending proposals.</p>;
  return (
    <ul className="task-list">
      {items.map((p) => (
        <li key={p.id} className="task-row">
          <div className="task-main">
            <span className="cell-strong">{p.recommendation} <EmployeeCode employeeId={p.params?.employee_id} /></span>
            <span className="task-meta">{p.recommendation_type} · {(p.reason || '').slice(0, 100)}</span>
          </div>
          <div className="cell-actions" style={{ display: 'flex', gap: 6 }}>
            <button type="button" className="btn-small" disabled={!!busy} onClick={() => decide(p.id, 'APPROVED')}>
              {busy === p.id + 'APPROVED' ? '…' : 'Approve'}
            </button>
            <button type="button" className="btn-small" disabled={!!busy} onClick={() => decide(p.id, 'REJECTED')}>
              {busy === p.id + 'REJECTED' ? '…' : 'Reject'}
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}

// Persistent mini player: one voice entry point on every page. It lives in
// a fixed dock (bottom-right default, bottom-center optional) and is never
// draggable. Collapsed it is an orb pill; expanded it is a compact card
// with live state, transcript, proposals and session controls.
export default function MiniPlayer({ hidden, onOpenJarvis }) {
  const voice = useVoice();
  const [expanded, setExpanded] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);
  const [dock, setDock] = useState(() => {
    try {
      return window.localStorage.getItem(DOCK_KEY) === 'bc' ? 'bc' : 'br';
    } catch {
      return 'br';
    }
  });

  const session = voice?.session;
  const roomState = voice?.roomState || { assistantState: 'idle', remoteCount: 0, transcript: [] };
  const voiceStatus = voice?.voiceStatus;

  // Pending-proposals badge (existing endpoint, light poll).
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await api.proposalsPending();
        if (!cancelled) setPendingCount(Array.isArray(data) ? data.length : 0);
      } catch { /* ignore */ }
    };
    load();
    const t = setInterval(load, 8000);
    return () => { cancelled = true; clearInterval(t); };
  }, []);

  // Drop any stale free-form position saved by the old draggable player.
  useEffect(() => {
    try {
      window.localStorage.removeItem(STALE_POS_KEY);
    } catch { /* private mode: nothing to clean */ }
  }, []);

  // Esc collapses the card.
  useEffect(() => {
    if (!expanded) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setExpanded(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [expanded]);

  const setDockPersist = (d) => {
    setDock(d === 'bc' ? 'bc' : 'br');
    try {
      window.localStorage.setItem(DOCK_KEY, d === 'bc' ? 'bc' : 'br');
    } catch { /* private mode: state just won't persist */ }
  };

  if (!voice || !session || hidden) return null;

  const label = voiceStateLabel(session, roomState);
  const orbState = session.phase === 'error' ? 'error'
    : session.phase === 'live'
      ? (roomState.assistantState === 'speaking' ? 'speaking'
        : roomState.assistantState === 'thinking' ? 'thinking'
        : roomState.assistantState === 'listening' ? 'listening' : 'live')
      : (session.phase === 'idle' ? 'idle' : 'connecting');
  const inSession = session.creds && session.phase !== 'idle' && session.phase !== 'error';
  const notReady = voiceStatus && !voiceStatus.configured;
  const dockClass = dock === 'bc' ? 'dock-bc' : 'dock-br';

  if (!expanded) {
    return (
      <div className={`miniplayer ${dockClass}`}>
        <button
          type="button"
          className="mini-orb-btn"
          aria-label={inSession ? `Jarvis mini player, ${label}. Activate to expand.` : 'Open Jarvis mini player'}
          onClick={() => setExpanded(true)}
        >
          <span className={`mini-orb orb-${orbState}`} aria-hidden="true" />
          {pendingCount > 0 && (
            <span className="mini-badge" aria-label={`${pendingCount} pending proposals`}>{pendingCount}</span>
          )}
        </button>
      </div>
    );
  }

  return (
    <div className={`miniplayer mini-card ${dockClass}`} role="dialog" aria-label="Jarvis mini player">
      <div className="mini-head">
        <span className={`mini-orb orb-${orbState} small`} aria-hidden="true" />
        <strong>Jarvis · {label}</strong>
        <span className="mini-dockswitch" role="group" aria-label="Dock position">
          <button
            type="button"
            className={dock === 'br' ? 'dock-on' : ''}
            aria-pressed={dock === 'br'}
            aria-label="Dock bottom right"
            title="Dock bottom right"
            onClick={() => setDockPersist('br')}
          >
            Right
          </button>
          <button
            type="button"
            className={dock === 'bc' ? 'dock-on' : ''}
            aria-pressed={dock === 'bc'}
            aria-label="Dock bottom center"
            title="Dock bottom center"
            onClick={() => setDockPersist('bc')}
          >
            Center
          </button>
        </span>
        <span className="mini-head-actions">
          <button type="button" className="btn-small" onClick={() => setExpanded(false)} aria-label="Minimize mini player">–</button>
        </span>
      </div>
      <div className="mini-body">
        {!inSession ? (
          <>
            <p className="muted">Talk to Jarvis hands-free. Starts a fresh room each time.</p>
            {notReady ? (
              <p className="form-errors" role="status">
                Voice not configured
                {voiceStatus?.missing?.length > 0 ? ` (missing: ${voiceStatus.missing.join(', ')} in backend/.env)` : ''}.
              </p>
            ) : (
              <button type="button" className="btn-primary" onClick={session.start}>🎤 Start voice</button>
            )}
          </>
        ) : (
          <>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <StatusBadge tone={orbState === 'speaking' ? 'info' : orbState === 'listening' ? 'ok' : 'neutral'}>
                {label}
              </StatusBadge>
              <button type="button" className="btn-small" onClick={() => session.setMuted(!session.muted)}>
                {session.muted ? '🔇 Unmute' : '🎤 Mute'}
              </button>
              <button type="button" className="btn-small" onClick={session.end}>⏹ End</button>
            </div>
            {roomState.transcript.length > 0 && (
              <ul className="mini-transcript" aria-label="Live transcript">
                {roomState.transcript.slice(-4).map((t, i) => (
                  <li key={i}><b>{t.who}:</b> {(t.text || '').slice(0, 160)}</li>
                ))}
              </ul>
            )}
            {!session.agentJoined && (
              <p className="muted">Waiting for agent… start it: <span className="cell-mono">cd Jarvis, then uv run src/agent.py dev</span></p>
            )}
          </>
        )}
        {session.error && <p className="form-errors" role="alert" style={{ marginTop: 8 }}>{session.error}</p>}
        <div style={{ marginTop: 8 }}>
          <ActivityStrip compact />
        </div>
        <div style={{ marginTop: 8 }}>
          <ProposalMiniList />
        </div>
        <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
          <button type="button" className="btn-secondary" onClick={onOpenJarvis}>Open full Jarvis</button>
        </div>
      </div>
    </div>
  );
}
