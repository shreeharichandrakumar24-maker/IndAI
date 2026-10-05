import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../services/api';

// Voice session state machine (Part D). The single LiveKitRoom lives in
// VoiceContext (SharedRoom); this hook owns token + lifecycle +
// agent-presence timeout and is mounted ONCE by the app-level provider.
// States: idle | connecting | waiting-agent | live | error. Never throws;
// the rest of the site works when voice is unavailable.
const AGENT_WAIT_MS = 15000;

export default function useVoiceSession() {
  const [phase, setPhase] = useState('idle');
  const [creds, setCreds] = useState(null);
  const [error, setError] = useState('');
  const [muted, setMuted] = useState(false);
  const [agentJoined, setAgentJoined] = useState(false);
  const waitTimer = useRef(null);

  const clearTimer = () => {
    if (waitTimer.current) {
      clearTimeout(waitTimer.current);
      waitTimer.current = null;
    }
  };

  useEffect(() => clearTimer, []);

  const start = useCallback(async () => {
    setError('');
    setAgentJoined(false);
    setPhase('connecting');
    try {
      const tok = await api.voiceToken();
      if (!tok || !tok.token || !tok.url) throw new Error('Bad token response.');
      setCreds(tok);
      setPhase('waiting-agent');
      clearTimer();
      waitTimer.current = setTimeout(() => {
        setAgentJoined((joined) => {
          if (!joined) setError('Voice agent is not running. Start it with: cd Jarvis, then uv run src/agent.py dev (or the venv python directly).');
          return joined;
        });
      }, AGENT_WAIT_MS);
    } catch (err) {
      const msg = String(err.message || '');
      if (msg.includes('503')) {
        setError('Voice not configured on the server (LIVEKIT_* missing in backend/.env).');
      } else if (/permission|denied|NotAllowed/i.test(msg)) {
        setError('Microphone permission denied. Allow the mic and retry.');
      } else {
        setError(msg || 'Could not start the voice session.');
      }
      setPhase('error');
    }
  }, []);

  const handleRoomConnected = useCallback(() => {
    setPhase((p) => (p === 'connecting' || p === 'waiting-agent' ? 'waiting-agent' : p));
  }, []);

  const handleAgentSeen = useCallback(() => {
    setAgentJoined(true);
    clearTimer();
    setError('');
    setPhase('live');
  }, []);

  const handleRoomDisconnected = useCallback(() => {
    clearTimer();
    setCreds(null);
    setAgentJoined(false);
    setMuted(false);
    setPhase('idle');
  }, []);

  const end = useCallback(() => {
    handleRoomDisconnected();
  }, [handleRoomDisconnected]);

  const handleRoomError = useCallback((message) => {
    clearTimer();
    setAgentJoined(false);
    setError(message || 'Voice connection lost. Check the network and press Start voice to reconnect.');
    setPhase('error');
  }, []);

  const retry = useCallback(async () => {
    await start();
  }, [start]);

  return {
    phase, creds, error, muted, setMuted, agentJoined,
    start, end, retry, handleRoomConnected, handleAgentSeen, handleRoomDisconnected,
    handleRoomError,
  };
}
