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
// assistant state + transcript + remote count up to the provider.
function RoomChrome({ session, onUiCommand, onSnapshot }) {
  const { state: assistantState } = useVoiceAssistant();
  const transcriptions = useTranscriptions();
  const remotes = useRemoteParticipants();
  const { localParticipant } = useLocalParticipant();

  useEffect(() => {
    if (!localParticipant) return undefined;
    let cancelled = false;
    (async () => {
      try {
        await localParticipant.registerRpcMethod(UI_COMMAND_METHOD, async (data) => {
          if (cancelled) return 'rejected: disconnecting';
          const verdict = validateUiCommand(data.payload);
          if (!verdict.ok) return verdict.error;
          try {
            const nav = await onUiCommand(verdict.action, verdict.args);
            return nav || 'ok';
          } catch (err) {
            return `rejected: ${String(err.message || err).slice(0, 200)}`;
          }
        });
      } catch {
        // registration failures surface via the session error state
      }
    })();
    return () => { cancelled = true; };
  }, [localParticipant, onUiCommand]);

  useEffect(() => {
    if (!localParticipant) return;
    try {
      localParticipant.setMicrophoneEnabled(!session.muted);
    } catch { /* ignore */ }
  }, [localParticipant, session.muted]);

  useEffect(() => {
    onSnapshot({
      assistantState,
      remoteCount: remotes.length,
      transcript: transcriptions.slice(-8).map((t) => ({
        who: t.participantInfo?.identity?.startsWith('admin-') ? 'You' : 'Jarvis',
        text: t.text,
      })),
    });
  }, [assistantState, remotes.length, transcriptions, onSnapshot]);

  return null;
}

// One LiveKitRoom for the app, mounted as long as a session is active.
// It is a sibling of the page content, so switching pages never unmounts it.
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
      onError={() => session.end()}
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
    const key = `${snap.assistantState}|${snap.remoteCount}|${snap.transcript.length}|${lastText}`;
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
