import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../services/api';
import StatusBadge from '../components/StatusBadge';
import VoicePicker from '../components/VoicePicker';
import { ProposalMiniList } from '../components/voice/MiniPlayer';
import { ActivityStrip, useCommandFeed } from '../components/voice/CommandFeed';
import { useVoice, voiceStateLabel } from '../components/voice/useVoice';
import { parseNavigationRequest, validateUiCommand } from '../components/voice/uiCommand';
import { NAV_ITEMS } from '../config/nav';

const CHIPS = [
  'Which machines need attention?',
  'Show me M-001',
  'Which employees are available for welding?',
  'Assign the welding task to the best person',
  'What happens if M-001 is down for four hours?',
];

// Full Jarvis page. It reads the SHARED app-level voice session (see
// VoiceContext) — navigating here never restarts the room, mic or
// transcript, and the mini player + page stay in sync. Typed fallback,
// checklist, chips and proposals are unchanged.
// Layout: status header on top, then a two-column grid (conversation card
// with its own scroll + pinned input on the left, checklist/chips/proposals
// on the right) collapsing to one column below ~1000px.
const ORB_CLASS = {
  speaking: 'orb-speaking', thinking: 'orb-thinking', listening: 'orb-listening',
};

export default function Jarvis({ onUiCommand }) {
  const voice = useVoice();
  const session = voice.session;
  const roomState = voice.roomState;
  const voiceStatus = voice.voiceStatus;
  const [micState, setMicState] = useState('unknown');
  const [typedInput, setTypedInput] = useState('');
  const [typedBusy, setTypedBusy] = useState(false);
  const [typedReply, setTypedReply] = useState(null);
  const feed = useCommandFeed();
  const transcriptRef = useRef(null);
  const micSupported = typeof window !== 'undefined' &&
    !!(window.SpeechRecognition || window.webkitSpeechRecognition || navigator.mediaDevices?.getUserMedia);

  useEffect(() => {
    if (navigator.permissions?.query) {
      let cancelled = false;
      navigator.permissions.query({ name: 'microphone' }).then(
        (r) => { if (!cancelled) setMicState(r.state); },
        () => {},
      );
      return () => { cancelled = true; };
    }
    return undefined;
  }, []);

  const inSession = session.creds && session.phase !== 'idle' && session.phase !== 'error';
  const assistantState = roomState.assistantState;
  const label = voiceStateLabel(session, roomState);
  const orbState = assistantState === 'speaking' ? 'speaking'
    : assistantState === 'thinking' ? 'thinking'
    : assistantState === 'listening' ? 'listening' : 'live';
  const voiceTranscript = roomState.transcript.slice(-6);
  const lastTranscriptText = voiceTranscript.length > 0
    ? voiceTranscript[voiceTranscript.length - 1].text : '';

  // Keep the newest message visible inside the conversation card.
  useEffect(() => {
    const el = transcriptRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [voiceTranscript.length, lastTranscriptText, typedReply, typedBusy]);

  const sendTyped = useCallback(async (text) => {
    const msg = (text ?? typedInput).trim();
    if (!msg || typedBusy) return;
    setTypedInput('');
    // Typed navigation uses the shared alias map + the same strict
    // validator/handler as the voice RPC path.
    const nav = parseNavigationRequest(msg);
    if (nav && onUiCommand) {
      const verdict = validateUiCommand(nav.filter
        ? { action: 'navigate', page: nav.page, filter: nav.filter }
        : { action: 'navigate', page: nav.page });
      if (verdict.ok) {
        let res = 'ok';
        try { res = (await onUiCommand(verdict.action, verdict.args)) || 'ok'; }
        catch (err) { res = `rejected: ${err?.message || err}`; }
        const label = NAV_ITEMS.find((n) => n.id === nav.page)?.label || nav.page;
        const reply = res === 'ok' ? `Opening ${label}.` : String(res).replace(/^rejected: ?/, '');
        setTypedReply({ q: msg, a: reply, actions: [], commands: [] });
        return;
      }
    }
    setTypedBusy(true);
    try {
      const res = await api.assistantChat([{ role: 'user', content: msg }]);
      setTypedReply({
        q: msg, a: res.reply,
        actions: res.proposed_actions || [],
        commands: res.commands || [],
      });
    } catch (err) {
      setTypedReply({ q: msg, a: `Failed: ${err.message}`, actions: [] });
    } finally {
      setTypedBusy(false);
    }
  }, [typedInput, typedBusy, onUiCommand]);

  const checklist = voiceStatus ? [
    { label: 'Voice configured', ok: voiceStatus.configured, hint: !voiceStatus.configured && voiceStatus.missing?.length > 0 ? `missing: ${voiceStatus.missing.join(', ')}` : '' },
    { label: 'Token OK', ok: ['connecting', 'waiting-agent', 'live'].includes(session.phase) || session.agentJoined },
    { label: 'Connected', ok: ['waiting-agent', 'live'].includes(session.phase) || session.agentJoined },
    { label: 'Agent joined', ok: session.agentJoined, hint: !session.agentJoined && inSession ? 'start it: cd Jarvis, then uv run src/agent.py dev' : '' },
    { label: 'Mic permission', ok: micState === 'granted', hint: micState === 'granted' ? '' : `browser says: ${micState}` },
  ] : [];

  return (
    <div className="page jarvis-page">
      <div className="page-head">
        <div>
          <h2>Jarvis</h2>
          <p className="page-desc">Realtime voice agent. Talk, interrupt, and tap Approve for proposals. Typed chat below works without voice.</p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <StatusBadge tone="info">AI voice labeled</StatusBadge>
        </div>
      </div>

      <section className="panel jarvis-hero jarvis-status" aria-label="Voice session status">
        <div className="jarvis-status-main">
          {!inSession ? (
            <>
              <p className="muted">Starts a fresh LiveKit room and dispatches the voice agent.</p>
              <button type="button" className="btn-primary btn-hero" onClick={session.start}>
                🎤 Start voice
              </button>
            </>
          ) : (
            <>
              <div
                className={`jarvis-orb jarvis-orb-sm ${ORB_CLASS[orbState] || ''}`}
                aria-label={`Jarvis is ${label}`}
              />
              <p className="muted" role="status">
                {assistantState} · {roomState.remoteCount > 0 ? 'agent joined' : 'waiting for agent…'}
              </p>
              {(roomState.agentVoiceStatus || '') === 'llm_failed' && (
                <p className="muted" role="status">Voice model not responding — navigation still works.</p>
              )}
              <div style={{ display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap' }}>
                <button type="button" className="btn-small" onClick={() => session.setMuted(!session.muted)}>
                  {session.muted ? '🔇 Unmute' : '🎤 Mute'}
                </button>
                <button type="button" className="btn-secondary" onClick={session.end}>⏹ End voice</button>
              </div>
            </>
          )}
          {session.error && (
            <p className="form-errors" role="alert" style={{ marginTop: 8 }}>
              {session.error}{' '}
              {session.phase === 'error' && (
                <button type="button" className="btn-small" onClick={() => (session.retry ? session.retry() : session.start())}>↻ Reconnect</button>
              )}
            </p>
          )}
        </div>
        <div className="jarvis-status-side">
          <VoicePicker />
        </div>
      </section>

      <div className="jarvis-grid">
        <section className="panel jarvis-convo" aria-label="Conversation">
          <h2>Conversation</h2>
          <div className="jarvis-transcript" ref={transcriptRef} tabIndex={0} aria-label="Conversation transcript">
            {voiceTranscript.length === 0 && !typedReply && !typedBusy && (
              <p className="muted">Start voice above — or just type below. Everything you say and hear lands here.</p>
            )}
            {voiceTranscript.length > 0 && (
              <ul className="task-list">
                {voiceTranscript.map((t, i) => (
                  <li key={i} className="task-row">
                    <div className="task-main">
                      <span className="cell-strong">{t.who === 'You' ? 'You' : '✦ Jarvis'}</span>
                      <span className="task-meta" style={{ whiteSpace: 'pre-wrap' }}>{t.text}</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {typedBusy && <p className="muted">Thinking…</p>}
            {typedReply && (
              <div className="panel" style={{ margin: 0 }}>
                <p><b>You:</b> {typedReply.q}</p>
                <p><b>✦ Assistant:</b> {typedReply.a}</p>
                {(typedReply.commands || []).map((c) => (
                  <p key={c.command_id} style={{ marginTop: 4 }}>
                    {c.undo_available && (
                      <button
                        type="button"
                        className="btn-small"
                        onClick={async () => {
                          try { await feed?.undo(c.command_id); } catch { /* 409 shown next poll */ }
                        }}
                      >
                        Undo
                      </button>
                    )}
                  </p>
                ))}
                {(typedReply.actions || []).map((a) => (
                  <p key={a.id || a.title} className="muted">Suggested: {a.title} ({a.action_type}) — approve in Pending proposals.</p>
                ))}
              </div>
            )}
          </div>
          <form className="jarvis-inputrow" onSubmit={(e) => { e.preventDefault(); sendTyped(); }}>
            <input value={typedInput} onChange={(e) => setTypedInput(e.target.value)} placeholder="Ask in plain words…" aria-label="Type a message to the assistant" style={{ flex: 1 }} maxLength={2000} disabled={typedBusy} />
            <button type="submit" className="btn-primary" disabled={typedBusy || !typedInput.trim()}>Send</button>
          </form>
        </section>

        <div className="jarvis-rail">
          <section className="panel">
            <h2>Status checklist</h2>
            {checklist.length === 0 ? <p className="muted">Loading…</p> : (
              <ul className="task-list">
                {checklist.map((c) => (
                  <li key={c.label} className="task-row">
                    <div className="task-main">
                      <span className="cell-strong">{c.ok ? '✓' : '○'} {c.label}</span>
                      {c.hint && <span className="task-meta">{c.hint}</span>}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="panel">
            <h2>Try saying</h2>
            <div className="no-print" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {CHIPS.map((chip) => (
                <button key={chip} type="button" className="btn-small" onClick={() => sendTyped(chip)} disabled={typedBusy}>{chip}</button>
              ))}
            </div>
          </section>

          <section className="panel">
            <h2>Jarvis activity</h2>
            <ActivityStrip />
          </section>

          <section className="panel">
            <h2>Pending proposals</h2>
            <ProposalMiniList />
          </section>
        </div>
      </div>
    </div>
  );
}
