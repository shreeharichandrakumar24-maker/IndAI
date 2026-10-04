import { createContext, useContext } from 'react';

// Shared voice context object + accessor + state label. Kept in its own
// module (no components) so Fast Refresh stays quiet and both the provider
// (VoiceContext) and the consumers (MiniPlayer, Jarvis page) import from one
// place. LiveKit logic itself is untouched.
export const VoiceCtx = createContext(null);

export function useVoice() {
  return useContext(VoiceCtx);
}

export function voiceStateLabel(session, roomState) {
  if (session.phase === 'live' && roomState.assistantState && roomState.assistantState !== 'idle') {
    return roomState.assistantState;
  }
  return { idle: 'idle', connecting: 'connecting…', 'waiting-agent': 'waiting for agent…', live: 'live', error: 'error' }[session.phase] || session.phase;
}
