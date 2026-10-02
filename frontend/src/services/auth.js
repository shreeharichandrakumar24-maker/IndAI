// Minimal Supabase Auth (GoTrue) client over plain fetch — no extra deps.
// Managers create accounts in the Supabase dashboard (Authentication -> Users);
// this web app is sign-in only. Session (access + refresh tokens) persists in
// localStorage. api.js attaches the access token to every backend call.
const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || 'https://qxhwsuzzdwjmpfdqwwri.supabase.co';
const SUPABASE_ANON_KEY =
  import.meta.env.VITE_SUPABASE_ANON_KEY || 'sb_publishable_ZfvvUO6OQ3VlYUBvNCrMaw_hbfkEQ-n';

const LS_KEY = 'indai.auth.session';

export function loadSession() {
  try {
    const s = JSON.parse(localStorage.getItem(LS_KEY) || 'null');
    if (s && s.access_token && s.expires_at && s.expires_at * 1000 > Date.now() + 60000) return s;
    return s && s.access_token ? s : null; // expired-but-present: try refresh first
  } catch {
    return null;
  }
}

function saveSession(s) {
  if (s) localStorage.setItem(LS_KEY, JSON.stringify(s));
  else localStorage.removeItem(LS_KEY);
}

async function tokenCall(path, body, token) {
  const res = await fetch(`${SUPABASE_URL}/auth/v1${path}`, {
    method: 'POST',
    headers: {
      apikey: SUPABASE_ANON_KEY,
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) {
    let msg = `Auth failed (${res.status})`;
    try {
      const j = await res.json();
      if (j.msg || j.error_description || j.error) msg = j.msg || j.error_description || j.error;
    } catch { /* ignore */ }
    throw new Error(msg);
  }
  return res.json();
}

export async function signIn(email, password) {
  const data = await tokenCall('/token?grant_type=password', { email, password });
  const session = {
    access_token: data.access_token,
    refresh_token: data.refresh_token,
    expires_at: Math.floor(Date.now() / 1000) + (data.expires_in || 3600),
    email: data.user?.email || email,
  };
  saveSession(session);
  window.dispatchEvent(new Event('indai-auth'));
  return session;
}

export async function refreshSession() {
  const s = loadSession();
  if (!s?.refresh_token) return null;
  try {
    const data = await tokenCall('/token?grant_type=refresh_token', { refresh_token: s.refresh_token });
    const next = {
      access_token: data.access_token,
      refresh_token: data.refresh_token || s.refresh_token,
      expires_at: Math.floor(Date.now() / 1000) + (data.expires_in || 3600),
      email: data.user?.email || s.email,
    };
    saveSession(next);
    return next;
  } catch {
    return null;
  }
}

export function signOut() {
  const s = loadSession();
  if (s?.access_token) tokenCall('/logout', {}, s.access_token).catch(() => {});
  saveSession(null);
  window.dispatchEvent(new Event('indai-auth'));
}

export function accessToken() {
  return loadSession()?.access_token || null;
}

export { SUPABASE_URL };
