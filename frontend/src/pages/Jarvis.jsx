import { useEffect, useRef, useState } from 'react';
import { api } from '../services/api';
import StatusBadge from '../components/StatusBadge';
import VoicePicker from '../components/VoicePicker';
import { isVoiceOn, speakText, speechSupported, stopSpeaking } from '../services/voice';

const WAKE_WORD = 'jarvis';
const WAKE_COOLDOWN_MS = 10 * 1000;

// Realtime Jarvis tab: tap to start listening, say "jarvis" to wake, talk.
// Replies stream sentence-by-sentence and are spoken as they arrive
// (barge-in: talking while Jarvis speaks cuts it off and takes the floor).
// Proposals still need Approve clicks — voice never auto-applies.
export default function Jarvis() {
  const [active, setActive] = useState(false);
  const [phase, setPhase] = useState('idle'); // idle|listening|thinking|speaking
  const [lines, setLines] = useState([]);
  const [wakeNote, setWakeNote] = useState('');
  const [lastWake, setLastWake] = useState(0);
  const recogRef = useRef(null);
  const activeRef = useRef(false);
  const phaseRef = useRef('idle');
  const historyRef = useRef([]);
  const setPhaseBoth = (p) => {
    phaseRef.current = p;
    setPhase(p);
  };

  const micSupported = typeof window !== 'undefined' &&
    (window.SpeechRecognition || window.webkitSpeechRecognition);

  const addLine = (who, text) => {
    setLines((ls) => [...ls.slice(-30), { who, text }]);
  };

  useEffect(() => () => {
    activeRef.current = false;
    try {
      recogRef.current?.abort();
    } catch { /* ignore */ }
    stopSpeaking();
  }, []);

  const speakQueue = useRef([]);

  const speakSentences = (sentences) => {
    // Shared speech queue: sentence events arrive while earlier ones still
    // play, so queue them and drain in order instead of cancelling.
    for (const s of sentences) {
      if (s && s.trim()) speakQueue.current.push(s.trim());
    }
    drainSpeech();
  };

  const drainSpeech = () => {
    if (!activeRef.current || phaseRef.current === 'speaking') return;
    const s = speakQueue.current.shift();
    if (!s) {
      setPhaseBoth(activeRef.current ? 'listening' : 'idle');
      return;
    }
    setPhaseBoth('speaking');
    addLine('jarvis', s);
    const ok = say(s, { onend: () => { setPhaseBoth('listening'); drainSpeech(); } });
    if (!ok) drainSpeech();
  };

  // Echo guard: the mic hears Jarvis's own speaker output. Everything
  // spoken in the last 20 s is remembered; transcripts matching it are
  // dropped before wake/barge-in/question handling. Genuine user speech
  // differs from TTS text, so barge-in keeps working.
  const spokenRef = useRef([]);
  const ECHO_MS = 20 * 1000;

  const logSpoken = (text) => {
    const clean = String(text || '').trim();
    if (!clean) return;
    const now = Date.now();
    spokenRef.current = [...spokenRef.current.filter((e) => now - e.at < ECHO_MS), { text: clean, at: now }].slice(-10);
  };

  const normWords = (s) => String(s || '').toLowerCase().replace(/[^a-z0-9\s]/g, ' ').split(/\s+/).filter(Boolean);

  const isEcho = (transcript) => {
    const heard = normWords(transcript);
    if (heard.length === 0) return false;
    const now = Date.now();
    const heardSet = new Set(heard);
    for (const entry of spokenRef.current) {
      if (now - entry.at > ECHO_MS) continue;
      const said = normWords(entry.text);
      if (said.length === 0) continue;
      // Either direction contains the other (partial mic pickup)...
      const heardStr = ` ${heard.join(' ')} `;
      const saidStr = ` ${said.join(' ')} `;
      if (heardStr.includes(saidStr) || saidStr.includes(heardStr)) return true;
      // ...or strong token overlap (Jaccard >= 0.55).
      const saidSet = new Set(said);
      let inter = 0;
      for (const w of heardSet) if (saidSet.has(w)) inter++;
      const jaccard = inter / new Set([...heardSet, ...saidSet]).size;
      if (jaccard >= 0.55) return true;
    }
    return false;
  };

  const say = (text, onend) => {
    logSpoken(text);
    return speakText(text, { onend });
  };

  const cutSpeech = () => {
    speakQueue.current = [];
    stopSpeaking();
  };

  const askBackend = async (text) => {
    setPhaseBoth('thinking');
    addLine('you', text);
    historyRef.current = [...historyRef.current.slice(-5), { role: 'user', content: text }];
    let reply = '';
    const actions = [];
    try {
      await api.assistantVoice(historyRef.current, (ev, data) => {
        if (!activeRef.current) return;
        if (ev === 'sentence' && data.text) {
          reply += (reply ? ' ' : '') + data.text;
          speakSentences([data.text]);
        } else if (ev === 'done') {
          for (const a of data.proposed_actions || []) actions.push(a);
        } else if (ev === 'error') {
          addLine('jarvis', `Sorry — ${data.detail || 'voice service failed.'}`);
          setPhaseBoth(activeRef.current ? 'listening' : 'idle');
        }
      });
      historyRef.current = [...historyRef.current.slice(-5), { role: 'assistant', content: reply }];
      if (actions.length > 0) {
        addLine('jarvis-action', JSON.stringify(actions));
      }
    } catch (err) {
      addLine('jarvis', `Sorry — ${err.message}`);
      setPhaseBoth(activeRef.current ? 'listening' : 'idle');
    }
  };

  const handleHeard = (transcript, isFinal) => {
    if (!activeRef.current) return;
    const lower = transcript.toLowerCase();
    // Echo first: own speaker output must never barge in, wake, or ask.
    if (isEcho(transcript)) return;
    // Barge-in: genuine talking while Jarvis speaks cuts it off.
    if (phaseRef.current === 'speaking' && lower.trim().length > 2) {
      cutSpeech();
      setPhaseBoth('listening');
    }
    if (!isFinal) return;
    // Wake word: single word "jarvis" (cooldown against repeats/misfires).
    if (lower.includes(WAKE_WORD)) {
      const now = Date.now();
      setLastWake((prev) => {
        if (now - prev < WAKE_COOLDOWN_MS) return prev;
        const greeting = 'Hey man, how can I help you?';
        setPhaseBoth('speaking');
        addLine('jarvis', greeting);
        say(greeting, { onend: () => { if (activeRef.current) setPhaseBoth('listening'); } });
        setWakeNote('Jarvis awake — talk now.');
        return now;
      });
      return;
    }    // Anything else heard while awake is a question (only when not speaking).
    if (phaseRef.current === 'listening' && transcript.trim()) {
      askBackend(transcript.trim());
    }
  };

  const start = () => {
    const Impl = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Impl) return;
    activeRef.current = true;
    setActive(true);
    setWakeNote(`Say "${WAKE_WORD}" to wake me.`);
    const recog = new Impl();
    recogRef.current = recog;
    recog.lang = 'en-US';
    recog.interimResults = true;
    recog.continuous = true;
    recog.onresult = (e) => {
      for (let i = e.resultIndex || 0; i < (e.results?.length || 0); i++) {
        const alt = e.results[i]?.[0];
        if (!alt) continue;
        handleHeard(alt.transcript || '', !!e.results[i].isFinal);
      }
    };
    recog.onend = () => {
      // Continuous mode: auto-restart while the tab session is active.
      if (activeRef.current) {
        try {
          recog.start();
        } catch { /* ignore */ }
      } else {
        setPhaseBoth('idle');
      }
    };
    recog.onerror = () => {
      if (activeRef.current) setWakeNote('Mic error — check permission, still listening.');
    };
    try {
      recog.start();
      setPhaseBoth('listening');
    } catch {
      activeRef.current = false;
      setActive(false);
    }
  };

  const stop = () => {
    activeRef.current = false;
    setActive(false);
    setPhaseBoth('idle');
    try {
      recogRef.current?.abort();
    } catch { /* ignore */ }
    cutSpeech();
    setWakeNote('');
  };

  const decide = async (act, decision) => {
    try {
      await api.decideRecommendation(act.id, decision, '');
      addLine('jarvis', decision === 'APPROVED' ? `Approved ${act.title} — applied.` : 'Rejected — nothing changed.');
    } catch (err) {
      addLine('jarvis', `Decision failed: ${err.message}`);
    }
  };

  const orbColor = phase === 'speaking' ? '#38bdf8' : phase === 'thinking' ? '#f59e0b' : phase === 'listening' ? '#22c55e' : '#64748b';

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>Jarvis</h2>
          <p className="page-desc">Realtime voice. Say “jarvis” to wake. Talking while it speaks interrupts. Actions still need your tap.</p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <VoicePicker />
          <StatusBadge tone="info">AI voice labeled</StatusBadge>
        </div>
      </div>

      {!micSupported && (
        <div className="alert-banner" role="alert">
          Voice input needs Chrome or Edge. Text chat stays available on the AI Assistant page.
        </div>
      )}

      <section className="panel" style={{ textAlign: 'center', padding: '32px 16px' }}>
        <div
          aria-label={`Jarvis is ${phase}`}
          style={{
            width: 120, height: 120, borderRadius: '50%', margin: '0 auto 16px',
            background: `radial-gradient(circle, ${orbColor} 0%, transparent 70%)`,
            border: `3px solid ${orbColor}`,
            transition: 'border-color 0.3s',
          }}
        />
        <p className="muted" role="status">
          {!active ? 'Tap Start, then say “jarvis”.' : `${phase}…`}
          {wakeNote && active ? ` ${wakeNote}` : ''}
          {!isVoiceOn() && active ? ' (voice replies muted — toggle in AI Assistant)' : ''}
        </p>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 12 }}>
          {!active ? (
            <button type="button" className="btn-primary" disabled={!micSupported} onClick={start}>🎤 Start listening</button>
          ) : (
            <button type="button" className="btn-secondary" onClick={stop}>⏹ Stop</button>
          )}
        </div>
      </section>

      <section className="panel">
        <h2>Conversation</h2>
        {lines.length === 0 ? <p className="muted">Nothing said yet.</p> : (
          <ul className="task-list">
            {lines.map((l, i) => l.who === 'jarvis-action' ? (
              <li key={i} className="task-row">
                <ActionCard raw={l.text} onDecide={decide} />
              </li>
            ) : (
              <li key={i} className="task-row">
                <div className="task-main">
                  <span className="cell-strong">{l.who === 'you' ? 'You' : '✦ Jarvis'}</span>
                  <span className="task-meta" style={{ whiteSpace: 'pre-wrap' }}>{l.text}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function ActionCard({ raw, onDecide }) {
  const [acts] = useState(() => {
    try {
      return JSON.parse(raw);
    } catch {
      return [];
    }
  });
  const [done, setDone] = useState({});
  if (!Array.isArray(acts) || acts.length === 0) return null;
  return (
    <div className="task-main" style={{ width: '100%' }}>
      {acts.map((a) => (
        <div key={a.id} className="panel" style={{ marginTop: 8 }}>
          <p><b>{a.title}</b> <StatusBadge tone="warn">{a.action_type}</StatusBadge></p>
          {done[a.id] ? <p className="muted">{done[a.id]}</p> : (
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="button" className="btn-primary" onClick={async () => {
                await onDecide(a, 'APPROVED');
                setDone((d) => ({ ...d, [a.id]: 'Approved — applied.' }));
              }}>Approve</button>
              <button type="button" className="btn-secondary" onClick={async () => {
                await onDecide(a, 'REJECTED');
                setDone((d) => ({ ...d, [a.id]: 'Rejected.' }));
              }}>Reject</button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
