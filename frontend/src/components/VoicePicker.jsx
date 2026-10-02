import { useEffect, useState } from 'react';
import { loadVoices, savedVoiceURI, saveVoiceURI, speechSupported } from '../services/voice';

// Voice picker: choose a different TTS voice, persisted site-wide.
// Renders nothing where speech is unsupported.
export default function VoicePicker({ onChanged }) {
  const [voices, setVoices] = useState([]);
  const [current, setCurrent] = useState(() => savedVoiceURI());

  useEffect(() => {
    let cancelled = false;
    loadVoices().then((list) => {
      if (!cancelled) setVoices(list);
    });
    return () => { cancelled = true; };
  }, []);

  if (!speechSupported() || voices.length === 0) return null;

  const choose = (uri) => {
    setCurrent(uri);
    saveVoiceURI(uri);
    if (onChanged) onChanged(uri);
  };

  return (
    <label className="muted" style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
      Voice
      <select value={current} onChange={(e) => choose(e.target.value)} title="Pick the spoken voice">
        <option value="">Auto (English first)</option>
        {voices.map((v) => (
          <option key={v.voiceURI} value={v.voiceURI}>
            {v.name} ({v.lang}){v.default ? ' ★' : ''}
          </option>
        ))}
      </select>
    </label>
  );
}
