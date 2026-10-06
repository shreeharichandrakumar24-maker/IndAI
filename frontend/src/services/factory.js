// Selected company/factory context (Part 1 + 9).
// Demo-grade, NOT authentication: a small localStorage record drives which
// factory the API is scoped to. A refresh keeps the selection; switching
// companies just overwrites it. No passwords, tokens or roles here.
const LS_KEY = 'indai.factory';

export function getSelectedFactory() {
  try {
    const raw = JSON.parse(localStorage.getItem(LS_KEY) || 'null');
    if (raw && raw.id) return raw;
  } catch { /* private mode / bad json */ }
  return null;
}

export function getSelectedFactoryId() {
  return getSelectedFactory()?.id || null;
}

export function setSelectedFactory(factory) {
  if (!factory || !factory.id) return;
  const next = { id: factory.id, name: factory.name || factory.id };
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(next));
  } catch { /* not persisted in private mode */ }
  window.dispatchEvent(new CustomEvent('indai-factory', { detail: next }));
  return next;
}

export function clearSelectedFactory() {
  try {
    localStorage.removeItem(LS_KEY);
  } catch { /* ignore */ }
  window.dispatchEvent(new CustomEvent('indai-factory', { detail: null }));
}

export function onFactoryChange(handler) {
  const fn = (e) => handler(e.detail || getSelectedFactory());
  window.addEventListener('indai-factory', fn);
  return () => window.removeEventListener('indai-factory', fn);
}
