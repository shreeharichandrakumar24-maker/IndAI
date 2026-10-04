import { useEffect, useRef, useState } from 'react';
import { api } from '../services/api';
import StatusBadge from '../components/StatusBadge';
import EmployeeCode from '../components/EmployeeCode';
import VoicePicker from '../components/VoicePicker';
import { useCommandFeed } from '../components/voice/CommandFeed';
import { isVoiceOn, setVoiceOn as persistVoice, speakText, stopSpeaking as stopVoice } from '../services/voice';

const CHIPS = [
  'What is happening in production?',
  'Which machines need attention?',
  'Which orders are at risk?',
  'Why is my order delayed?',
  'What should I do about the open incident?',
];

// Jarvis-style assistant (mobile-app Phase 4): bounded tool-loop chat with a
// visible "Data used" trace and Approve/Reject action cards. Every AI message
// is labeled; proposed actions execute only via the decision endpoint.
export default function Assistant() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [deciding, setDeciding] = useState('');
  const [decided, setDecided] = useState({});
  const [notes, setNotes] = useState({});
  const [showTrace, setShowTrace] = useState({});
  const [listening, setListening] = useState(false);
  const [heardNote, setHeardNote] = useState('');
  const [quick, setQuick] = useState(null);
  const [quickBusy, setQuickBusy] = useState(false);
  const [pending, setPending] = useState([]);
  const [decidingAll, setDecidingAll] = useState('');
  const feed = useCommandFeed();

  useEffect(() => {
    let cancelled = false;
    const loadPending = async () => {
      try {
        const data = await api.proposalsPending();
        if (!cancelled) setPending(Array.isArray(data) ? data : []);
      } catch { /* ignore; retried on next poll */ }
    };
    loadPending();
    const t = setInterval(loadPending, 5000);
    return () => { cancelled = true; clearInterval(t); };
  }, []);

  const decidePending = async (id, decision) => {
    setDecidingAll(id + decision);
    try {
      await api.decideRecommendation(id, decision, '');
      setPending((l) => l.filter((x) => x.id !== id));
    } catch { /* error line below covers it via next poll */ }
    finally {
      setDecidingAll('');
    }
  };
  const recogRef = useRef(null);

  const micSupported = typeof window !== 'undefined' &&
    (window.SpeechRecognition || window.webkitSpeechRecognition);
  const speechSupported = typeof window !== 'undefined' && 'speechSynthesis' in window;

  // Voice replies: shared site-wide voice lib (slice 1 behavior + picker).
  // Feature-detected — no speech API means today's text UI, zero breakage.
  const [voiceOn, setVoiceOn] = useState(() => isVoiceOn());
  const [speakingIdx, setSpeakingIdx] = useState(null);
  const voiceOnRef = useRef(voiceOn);
  voiceOnRef.current = voiceOn;

  const stopSpeaking = () => {
    stopVoice();
    setSpeakingIdx(null);
  };

  const toggleVoice = () => {
    setVoiceOn((v) => {
      const next = !v;
      persistVoice(next);
      if (!next) stopVoice();
      return next;
    });
  };

  const speak = (text, idx) => {
    if (!voiceOnRef.current || !text) return;
    setSpeakingIdx(idx);
    const ok = speakText(text, { onend: () => setSpeakingIdx((cur) => (cur === idx ? null : cur)) });
    if (!ok) setSpeakingIdx(null);
  };

  // Stop any speech when leaving the page.
  useEffect(() => () => {
    try {
      window.speechSynthesis?.cancel();
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    setQuickBusy(true);
    api.assistantQuick('overview').then((r) => setQuick(r)).catch(() => setQuick(null)).finally(() => setQuickBusy(false));
  }, []);

  const historyPayload = () => messages.slice(-10).map((m) => ({
    role: m.role === 'ai' ? 'assistant' : 'user',
    content: m.text,
  }));

  const send = async (text) => {
    const msg = (text ?? input).trim();
    if (!msg || busy) return;
    setInput('');
    setHeardNote('');
    stopSpeaking();
    setBusy(true);
    const payload = [...historyPayload(), { role: 'user', content: msg }];
    setMessages((ms) => [...ms, { role: 'user', text: msg }]);
    try {
      const res = await api.assistantChat(payload);
      const aiMsg = {
        role: 'ai', text: res.reply, trace: res.tool_trace || [], actions: res.proposed_actions || [],
        commands: res.commands || [],
      };
      setMessages((ms) => {
        speak(aiMsg.text, ms.length);
        return [...ms, aiMsg];
      });
    } catch (err) {
      const aiDown = String(err.message || '').includes('503');
      const aiMsg = {
        role: 'ai',
        text: aiDown
          ? 'The AI helper is unavailable right now (no AI key configured). Quick stats above still work — or assign work deterministically from the Tasks page: open a task and use Suggest assignment.'
          : `Sorry, that failed: ${err.message}`,
        trace: [], actions: [],
      };
      setMessages((ms) => {
        speak(aiMsg.text, ms.length);
        return [...ms, aiMsg];
      });
    } finally {
      setBusy(false);
    }
  };

  const decide = async (msgIdx, act) => {
    const key = `${msgIdx}:${act.id}`;
    setDeciding(key + act.decision);
    try {
      const res = await api.decideRecommendation(act.id, act.decision, notes[act.id] || '');
      setDecided((d) => ({ ...d, [key]: { decision: act.decision, result: res } }));
      // Spoken confirmation (slice 2): what was decided and what changed.
      const bits = [];
      if (act.decision === 'APPROVED') {
        bits.push('Approved.');
        if (res?.task_id) bits.push(`Task created. See the Tasks page.`);
        else if (res?.maintenance_id) bits.push('Repair scheduled. See Incidents.');
        else bits.push('Applied.');
      } else {
        bits.push('Rejected. Nothing changed.');
      }
      speak(bits.join(' '), `decide-${key}`);
    } catch (err) {
      setDecided((d) => ({ ...d, [key]: { decision: act.decision, error: err.message } }));
      speak(`Sorry, that failed: ${err.message}`, `decide-${key}-err`);
    } finally {
      setDeciding('');
    }
  };

  // Explicit start/stop recording: click to start, click again to stop.
  // Transcripts accumulate onto the input across sessions — speaking again
  // adds to the same sentence instead of replacing it. Nothing is sent
  // until you press Send. Interim results stream live while recording.
  const holdBase = useRef('');
  const inputRef = useRef('');
  inputRef.current = input;
  const stopListening = () => {
    // stop() only: delivers final results, then onend fires. abort() would
    // discard the last words, so it is never called on release.
    try {
      recogRef.current?.stop();
    } catch { /* ignore */ }
    setListening(false);
  };

  const startListening = () => {
    const Impl = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Impl || busy) return;
    stopSpeaking();
    // Capture what's already typed so this hold appends to it, not over it.
    holdBase.current = (inputRef.current || '').trim();
    const recog = new Impl();
    recogRef.current = recog;
    recog.lang = 'en-US';
    recog.interimResults = true;
    recog.continuous = false;
    let finalText = '';
    recog.onresult = (e) => {
      let interim = '';
      for (let i = e.resultIndex || 0; i < (e.results?.length || 0); i++) {
        const alt = e.results[i]?.[0];
        if (!alt) continue;
        if (e.results[i].isFinal) finalText += alt.transcript;
        else interim += alt.transcript;
      }
      const show = [holdBase.current, (finalText + ' ' + interim).trim()].filter(Boolean).join(' ');
      if (show) {
        setInput(show);
        setHeardNote('');
      }
    };
    recog.onend = () => {
      setListening(false);
      if (finalText.trim()) {
        const combined = [holdBase.current, finalText.trim()].filter(Boolean).join(' ');
        setInput(combined);
        // Repeat-back: show exactly what was heard for review before Send.
        setHeardNote(`Heard: "${finalText.trim()}" — review, then press Send.`);
      }
    };
    recog.onerror = () => setListening(false);
    try {
      recog.start();
      setListening(true);
      setHeardNote('');
    } catch {
      setListening(false);
    }
  };

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>AI Assistant</h2>
          <p className="page-desc">Ask about production, machines, orders and incidents. Suggestions apply only when you approve them.</p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <VoicePicker />
          {speechSupported && (
            <button type="button" className={voiceOn ? 'btn-primary' : 'btn-secondary'} onClick={toggleVoice} title={voiceOn ? 'Mute voice replies' : 'Unmute voice replies'}>
              {voiceOn ? '🔊 Voice on' : '🔇 Voice off'}
            </button>
          )}
          <StatusBadge tone="info">AI answers labeled</StatusBadge>
        </div>
      </div>

      <section className="panel">
        <h2>Right now {quickBusy ? <span className="muted">(loading…)</span> : null}</h2>
        {quick ? <p className="muted">{quick.summary}</p> : !quickBusy && <p className="muted">Quick stats unavailable.</p>}
        <div className="no-print" style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
          {['incidents', 'at-risk'].map((w) => (
            <button key={w} type="button" className="btn-small" onClick={() => send(w === 'incidents' ? 'Which machines need attention?' : 'Which orders are at risk?')} disabled={busy}>
              {w === 'incidents' ? 'Open incidents' : 'Orders at risk'}
            </button>
          ))}
        </div>
      </section>

      <section className="panel">
        <h2>Pending proposals ({pending.length})</h2>
        {pending.length === 0 ? (
          <p className="muted">Nothing waiting. Voice or smart-split proposals appear here for one-tap approval.</p>
        ) : (
          <ul className="task-list">
            {pending.map((p) => (
              <li key={p.id} className="task-row">
                <div className="task-main">
                  <span className="cell-strong">{p.recommendation} <EmployeeCode employeeId={p.params?.employee_id} /></span>
                  <span className="task-meta">{p.recommendation_type} · {(p.reason || '').slice(0, 120)}</span>
                </div>
                <div className="cell-actions" style={{ display: 'flex', gap: 6 }}>
                  <button type="button" className="btn-small" disabled={!!decidingAll} onClick={() => decidePending(p.id, 'APPROVED')}>
                    {decidingAll === p.id + 'APPROVED' ? '…' : 'Approve'}
                  </button>
                  <button type="button" className="btn-small" disabled={!!decidingAll} onClick={() => decidePending(p.id, 'REJECTED')}>
                    {decidingAll === p.id + 'REJECTED' ? '…' : 'Reject'}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel">
        <div className="no-print" style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
          {CHIPS.map((s) => (
            <button key={s} type="button" className="btn-small" onClick={() => send(s)} disabled={busy}>{s}</button>
          ))}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 12 }}>
          {messages.length === 0 && (
            <p className="muted">No questions yet. Try a suggestion above.</p>
          )}
          {messages.map((m, i) => (
            <div key={i} className="panel" style={{ margin: 0, background: m.role === 'user' ? 'var(--bg-panel-2)' : undefined }}>
              <p><b>{m.role === 'user' ? 'You' : '✦ Assistant'}</b> {m.role === 'ai' && <StatusBadge tone="info">AI</StatusBadge>}{' '}
                {m.role === 'ai' && speechSupported && (
                  <button type="button" className="btn-small" onClick={() => (speakingIdx === i ? stopSpeaking() : speak(m.text, i))} title={speakingIdx === i ? 'Stop speaking' : 'Read aloud'}>
                    {speakingIdx === i ? '⏹' : '🔊'}
                  </button>
                )}
              </p>
              <p style={{ whiteSpace: 'pre-wrap' }}>{m.text}</p>
              {m.role === 'ai' && (m.commands || []).map((c) => (
                c.undo_available ? (
                  <button
                    key={c.command_id}
                    type="button"
                    className="btn-small"
                    style={{ marginTop: 6 }}
                    onClick={async () => {
                      try {
                        await feed?.undo(c.command_id);
                        setNotes((n) => ({ ...n, [c.command_id]: 'undone' }));
                      } catch (err) {
                        setNotes((n) => ({ ...n, [c.command_id]: `Undo failed: ${err.message}` }));
                      }
                    }}
                  >
                    Undo
                  </button>
                ) : null
              ))}
              {m.role === 'ai' && (m.trace || []).length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <button type="button" className="btn-small" onClick={() => setShowTrace((s) => ({ ...s, [i]: !s[i] }))}>
                    {showTrace[i] ? 'Hide data used' : `Data used (${m.trace.length} lookups)`}
                  </button>
                  {showTrace[i] && (
                    <ul className="task-list" style={{ marginTop: 8 }}>
                      {m.trace.map((t, j) => (
                        <li key={j} className="task-row">
                          <div className="task-main">
                            <span className="cell-strong cell-mono">{t.tool}</span>
                            <span className="task-meta">{t.summary}</span>
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
              {(m.actions || []).map((a) => {
                const key = `${i}:${a.id}`;
                const done = decided[key];
                return (
                  <div key={a.id} className="panel" style={{ marginTop: 8 }}>
                    <p><b>{a.title}</b> <StatusBadge tone="warn">{a.action_type}</StatusBadge></p>
                    {a.detail && <p className="muted">{a.detail}</p>}
                    {done ? (
                      <p className="muted" role="status">
                        {done.error ? `Failed: ${done.error}`
                          : done.decision === 'APPROVED'
                            ? `Approved — action executed${done.result?.task_id ? ` (task ${String(done.result.task_id).slice(0, 8)}, see Tasks)` : ''}${done.result?.maintenance_id ? ` (maintenance ${String(done.result.maintenance_id).slice(0, 8)})` : ''}. See memory + the target page.`
                            : 'Rejected — nothing changed.'}
                      </p>
                    ) : (
                      <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                        <input
                          placeholder="Optional note"
                          value={notes[a.id] || ''}
                          onChange={(e) => setNotes((n) => ({ ...n, [a.id]: e.target.value }))}
                          style={{ flex: 1, minWidth: 160 }}
                        />
                        <button type="button" className="btn-primary" disabled={!!deciding} onClick={() => decide(i, { ...a, decision: 'APPROVED' })}>
                          {deciding === key + 'APPROVED' ? 'Saving…' : 'Approve'}
                        </button>
                        <button type="button" className="btn-secondary" disabled={!!deciding} onClick={() => decide(i, { ...a, decision: 'REJECTED' })}>
                          {deciding === key + 'REJECTED' ? 'Saving…' : 'Reject'}
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
          {busy && <p className="muted">Thinking…</p>}
        </div>

        {heardNote && !busy && (
          <p className="muted" role="status" style={{ marginBottom: 8 }}>{heardNote}</p>
        )}
        <form onSubmit={(e) => { e.preventDefault(); send(); }} style={{ display: 'flex', gap: 8 }}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={micSupported ? 'Ask in plain words… (or 🎤 Record to speak)' : 'Ask in plain words…'}
            style={{ flex: 1 }}
            maxLength={2000}
            disabled={busy}
          />
          {micSupported && (
            <button
              type="button"
              className={listening ? 'btn-primary' : 'btn-secondary'}
              onClick={() => {
                if (listening) stopListening();
                else startListening();
              }}
              title={listening ? 'Stop recording' : 'Start recording'}
            >
              {listening ? '⏹ Stop' : '🎤 Record'}
            </button>
          )}
          <button type="submit" className="btn-primary" disabled={busy || !input.trim()}>Send</button>
        </form>
      </section>
    </div>
  );
}
