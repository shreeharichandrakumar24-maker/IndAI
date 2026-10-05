import { useCallback, useEffect, useRef, useState } from 'react';
import {
  LiveKitRoom, RoomAudioRenderer,
  useLocalParticipant, useRemoteParticipants, useTranscriptions, useVoiceAssistant,
} from '@livekit/components-react';
import { api } from '../../services/api';
import useVoiceSession from '../../hooks/useVoiceSession';
import { UI_COMMAND_METHOD, validateUiCommand } from './uiCommand';
import { VoiceCtx } from './useVoice';

// Single app-level voice session (Phase 2). The useVoiceSession state
// machine lives here ONCE for the whole app lifetime, so starting voice and
// then navigating between pages never drops the room, mic or transcript.
// pages/Jarvis.jsx and MiniPlayer both read this context; neither owns a
// session anymore. LiveKit logic itself is untouched (hook + components).

// Runs INSIDE the shared room: registers the ui.command RPC once per
// participant (same strict whitelist validator), applies mute, and bridges
// assistant state + transcript + remote count up to the provider. The
// command handler is held in a ref so page/theme/sidebar changes never
// re-register or orphan the RPC mid-session; free text from the model is
// NEVER treated as a command, and nothing here ever says "disconnecting".
function RoomChrome({ session, onUiCommand, onSnapshot }) {
  const { state: assistantState } = useVoiceAssistant();
  const transcriptions = useTranscriptions();
  const remotes = useRemoteParticipants();
  const { localParticipant } = useLocalParticipant();
  const cmdRef = useRef(onUiCommand);
  const sessionRef = useRef(session);
  useEffect(() => { cmdRef.current = onUiCommand; }, [onUiCommand]);
  useEffect(() => { sessionRef.current = session; }, [session]);

  useEffect(() => {
    if (!localParticipant) return undefined;
    let disposed = false;
    // RPC handlers are keyed by method name on the participant: a second
    // registerRpcMethod for the same method THROWS and leaves the previous
    // (possibly disposed) closure active. So always unregister first, and
    // unregister on cleanup — the live closure always wins, and a stale one
    // can never keep answering after unmount.
    const methods = [UI_COMMAND_METHOD, 'voice.end_session'];
    (async () => {
      try {
        for (const m of methods) {
          try { localParticipant.unregisterRpcMethod(m); } catch { /* none registered */ }
        }
        await localParticipant.registerRpcMethod(UI_COMMAND_METHOD, async (data) => {
          // A late RPC landing after unmount must not speak "disconnecting":
          // return a retryable technical error the agent relays, not a
          // session-ending word.
          if (disposed) return 'rejected: voice command handler reloading, please retry';
          const verdict = validateUiCommand(data.payload);
          if (!verdict.ok) return verdict.error;
          try {
            const nav = await cmdRef.current(verdict.action, verdict.args);
            return nav || 'ok';
          } catch (err) {
            return `rejected: ${String(err.message || err).slice(0, 200)}`;
          }
        });
        await localParticipant.registerRpcMethod('voice.end_session', async () => {
          // Explicit user request only (agent end_session tool). Delay the
          // normal End flow so "Okay, ending the session." is heard first.
          if (disposed) return 'ok';
          setTimeout(() => { try { sessionRef.current.end(); } catch { /* ignore */ } }, 2500);
          return 'ok';
        });
      } catch (err) {
        // Never swallow: a failed registration means voice commands go
        // nowhere, and the agent needs the reason in its spoken errors.
        console.warn('[voice] ui.command RPC registration failed:', err?.message || err);
      }
    })();
    return () => {
      disposed = true;
      for (const m of methods) {
        try { localParticipant.unregisterRpcMethod(m); } catch { /* ignore */ }
      }
    };
  }, [localParticipant]);

  useEffect(() => {
    if (!localParticipant) return;
    try {
      localParticipant.setMicrophoneEnabled(!session.muted);
    } catch { /* ignore */ }
  }, [localParticipant, session.muted]);

  // The agent publishes a short model-health word as a participant
  // attribute (voice_status: ok | llm_failed). Surfaces in the Jarvis
  // page + mini player when the model is down (navigation still works).
  let agentVoiceStatus = '';
  try {
    const agentPeer = remotes.find((p) => !(p.identity || '').startsWith('admin-')) || remotes[0];
    agentVoiceStatus = agentPeer?.attributes?.voice_status || '';
  } catch { /* ignore */ }

  useEffect(() => {
    onSnapshot({
      assistantState,
      remoteCount: remotes.length,
      agentVoiceStatus,
      transcript: transcriptions.slice(-8).map((t) => ({
        who: t.participantInfo?.identity?.startsWith('admin-') ? 'You' : 'Jarvis',
        text: t.text,
      })),
    });
  }, [assistantState, remotes.length, transcriptions, agentVoiceStatus, onSnapshot]);

  return null;
}

// One LiveKitRoom for the app, mounted as long as a session is active.
// It is a sibling of the page content, so switching pages never unmounts it.
// The room NEVER disconnects on page/theme/sidebar change or on the Jarvis
// page unmounting: only the End button, the explicit voice.end_session RPC,
// a connection error (which lands in a reconnectable error state), or tab
// close ends it.
function SharedRoom({ session, onUiCommand, onSnapshot }) {
  if (!session.creds || session.phase === 'idle' || session.phase === 'error') return null;
  return (
    <LiveKitRoom
      serverUrl={session.creds.url}
      token={session.creds.token}
      audio
      video={false}
      connect
      onConnected={session.handleRoomConnected}
      onDisconnected={session.handleRoomDisconnected}
      onError={() => session.handleRoomError('Voice connection lost. Check the network and press Start voice to reconnect.')}
    >
      <RoomAudioRenderer />
      <RoomChrome session={session} onUiCommand={onUiCommand} onSnapshot={onSnapshot} />
    </LiveKitRoom>
  );
}

export default function VoiceProvider({ onUiCommand, children }) {
  const session = useVoiceSession();
  const [voiceStatus, setVoiceStatus] = useState(null);
  const [roomState, setRoomState] = useState({ assistantState: 'idle', remoteCount: 0, transcript: [] });
  const lastSnap = useRef('');

  // Server voice-config checklist: fetched once, reused by every surface.
  useEffect(() => {
    let cancelled = false;
    api.voiceStatus().then((st) => { if (!cancelled) setVoiceStatus(st); }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  // Bridge snapshots only propagate on real change (no render loops).
  const onSnapshot = useCallback((snap) => {
    const lastText = snap.transcript.length > 0 ? snap.transcript[snap.transcript.length - 1].text : '';
    const key = `${snap.assistantState}|${snap.remoteCount}|${snap.transcript.length}|${lastText}|${snap.agentVoiceStatus || ''}`;
    if (lastSnap.current !== key) {
      lastSnap.current = key;
      setRoomState(snap);
    }
  }, []);

  // Agent presence observed in the shared room marks the shared session live.
  useEffect(() => {
    if (roomState.remoteCount > 0) session.handleAgentSeen();
  }, [roomState.remoteCount, session]);

  const value = { session, voiceStatus, roomState };
  return (
    <VoiceCtx.Provider value={value}>
      {children}
      <SharedRoom session={session} onUiCommand={onUiCommand} onSnapshot={onSnapshot} />
    </VoiceCtx.Provider>
  );
}
