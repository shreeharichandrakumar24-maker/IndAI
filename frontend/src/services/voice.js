// Shared browser speech (TTS) for the whole site: Assistant replies,
// boss-view status readout, and anywhere else voice output is needed.
// Feature-detected: no speechSynthesis means no-ops, never breakage.
// Voice choice persists in localStorage ('indai.voiceURI'); on/off uses
// the existing 'indai.voice' key so the Assistant toggle keeps working.
export const VOICE_ON_KEY = 'indai.voice';
export const VOICE_URI_KEY = 'indai.voiceURI';

export function speechSupported() {
  return typeof window !== 'undefined' && 'speechSynthesis' in window;
}

export function isVoiceOn() {
  try {
    return localStorage.getItem(VOICE_ON_KEY) !== 'off';
  } catch {
    return true;
  }
}

export function setVoiceOn(on) {
  try {
    localStorage.setItem(VOICE_ON_KEY, on ? 'on' : 'off');
  } catch { /* ignore */ }
  if (!on) stopSpeaking();
}

export function savedVoiceURI() {
  try {
    return localStorage.getItem(VOICE_URI_KEY) || '';
  } catch {
    return '';
  }
}

export function saveVoiceURI(uri) {
  try {
    if (uri) localStorage.setItem(VOICE_URI_KEY, uri);
    else localStorage.removeItem(VOICE_URI_KEY);
  } catch { /* ignore */ }
}

// Voices load asynchronously in most browsers: resolve once available.
export function loadVoices() {
  return new Promise((resolve) => {
    if (!speechSupported()) {
      resolve([]);
      return;
    }
    const synth = window.speechSynthesis;
    const take = () => {
      try {
        const list = synth.getVoices() || [];
        if (list.length > 0) {
          resolve(sortVoices(list));
          return true;
        }
      } catch { /* ignore */ }
      return false;
    };
    if (take()) return;
    const timer = setTimeout(() => resolve(sortVoices(safeVoices())), 1500);
    try {
      synth.onvoiceschanged = () => {
        if (take()) clearTimeout(timer);
      };
    } catch {
      clearTimeout(timer);
      resolve([]);
    }
  });
}

function safeVoices() {
  try {
    return window.speechSynthesis?.getVoices() || [];
  } catch {
    return [];
  }
}

function sortVoices(list) {
  const score = (v) => {
    const lang = (v.lang || '').toLowerCase();
    let s = 0;
    if (lang.startsWith('en')) s += 10;
    if (v.default) s += 5;
    if ((v.name || '').toLowerCase().includes('google')) s += 2;
    if ((v.name || '').toLowerCase().includes('natural')) s += 1;
    return s;
  };
  return [...list].sort((a, b) => score(b) - score(a) || String(a.name).localeCompare(String(b.name)));
}

function pickVoice() {
  const list = safeVoices();
  if (list.length === 0) return null;
  const saved = savedVoiceURI();
  if (saved) {
    const found = list.find((v) => v.voiceURI === saved);
    if (found) return found;
  }
  return sortVoices(list)[0] || null;
}

export function stopSpeaking() {
  try {
    window.speechSynthesis?.cancel();
  } catch { /* ignore */ }
}

// Speak text (truncated for sanity). Returns true if speech started.
// onend/onerror always fire the callback so UI state can't stick.
export function speakText(text, { onend } = {}) {
  if (!speechSupported() || !isVoiceOn() || !text) return false;
  try {
    const synth = window.speechSynthesis;
    synth.cancel();
    const utter = new SpeechSynthesisUtterance(String(text).slice(0, 600));
    utter.lang = 'en-US';
    utter.voice = pickVoice();
    const done = () => {
      try {
        onend && onend();
      } catch { /* ignore */ }
    };
    utter.onend = done;
    utter.onerror = done;
    synth.speak(utter);
    return true;
  } catch {
    return false;
  }
}
