// Strict validator for the browser RPC method "ui.command" (Part D).
// Accepts ONLY the six whitelisted actions with correctly typed args.
// Anything else -> {ok:false, error} and the caller does nothing.
// Pure function: unit-tested without a browser.
//
// Rules (hard requirements):
// - navigate targets are EXACT page ids from config/nav.js (never URLs,
//   never arbitrary strings); the allowed list is derived from nav.js so it
//   can never drift.
// - Optional `filter` must be a canonical value from the per-page filter
//   list in shared/navigation.json (the ONE shared alias/preset source,
//   injected at startup by config/navigationData.js -> App.jsx).
// - Unknown top-level fields are rejected (strict shape per action).
// - Alias resolution (natural phrases -> page id) lives here too and is
//   used by the text assistant; Jarvis resolves with the same JSON.
import { NAV_ITEMS } from '../../config/nav.js';

const ACTIONS = ["navigate", "select_machine", "open_order", "open_incident",
  "focus_order_on_map", "show_proposals", "switch_company"];

// Top-level fields allowed per action (strict: anything else is rejected).
const ACTION_FIELDS = {
  navigate: ["page", "filter"],
  select_machine: ["machine"],
  open_order: ["order"],
  open_incident: ["incident"],
  focus_order_on_map: ["order"],
  show_proposals: [],
  switch_company: [],
};

// Shared alias data (shared/navigation.json), injected once at startup.
let NAV_DATA = { pages: {}, page_filters: {} };

export function setNavigationData(data) {
  if (data && typeof data === "object" && data.pages && typeof data.pages === "object") {
    NAV_DATA = data;
  }
}

function isNonEmptyString(v) {
  return typeof v === "string" && v.trim().length > 0;
}

// No URLs or script-like payloads ever pass through voice/typed commands.
function looksUnsafe(v) {
  const s = String(v).trim();
  if (/^(https?|javascript|data|file|ftp|blob|about):/i.test(s)) return true;
  if (/\/\//.test(s)) return true;
  if (/<\s*script|javascript\s*:|onerror\s*=|onload\s*=/i.test(s)) return true;
  return false;
}

const MAX_LEN = 120;

function navIds() {
  const ids = new Set(NAV_ITEMS.map((n) => n.id));
  ids.add("company");
  ids.add("onboarding");
  return ids;
}

function labelOf(id) {
  return NAV_ITEMS.find((n) => n.id === id)?.label || id;
}

// ---------------------------------------------------------------------------
// Alias resolution (shared rules come from shared/navigation.json).
// ---------------------------------------------------------------------------

function norm(text) {
  return String(text || "")
    .toLowerCase()
    .replace(/[.,!?;:'"()]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// Strip leading navigation verbs / filler ("please open the ..." -> "...").
const FILLER_RE = /^(?:please|ok|okay|hey|now|just|can you|could you|i want to|i would like to|i'd like to)\s+/;
const VERB_RE = /^(?:open|go to|navigate to|navigate|take me to|switch to|jump to|pull up|bring up|head to|goto|show me the|show me|show|display|load|bring me to)\b/;

function stripLead(s) {
  let out = s;
  let hadVerb = false;
  for (let i = 0; i < 4; i += 1) {
    const before = out;
    out = out.replace(FILLER_RE, "").trim();
    const m = out.match(VERB_RE);
    if (m) {
      out = out.slice(m[0].length);
      hadVerb = true;
    }
    out = out.replace(/^[\s:,-]+/, "").replace(/^(?:the|my|that)\s+/, "").trim();
    if (out === before) break;
  }
  return { text: out, hadVerb };
}

// Every intermediate form of the phrase (after each strip step), so an
// exact alias like "open incidents" is matched BEFORE "open" is stripped
// away as a verb.
function stateCandidates(s) {
  const out = [];
  const push = (t) => {
    if (!t) return;
    const t2 = stripTrail(t);
    if (!out.includes(t)) out.push(t);
    if (t2 && t2 !== t && !out.includes(t2)) out.push(t2);
  };
  let cur = s;
  push(cur);
  for (let i = 0; i < 4; i += 1) {
    const before = cur;
    cur = cur.replace(FILLER_RE, "").trim();
    const m = cur.match(VERB_RE);
    if (m) cur = cur.slice(m[0].length);
    cur = cur.replace(/^[\s:,-]+/, "").replace(/^(?:the|my|that)\s+/, "").trim();
    if (cur === before) break;
    push(cur);
  }
  return out;
}

function stripTrail(s) {
  return s
    .replace(/(?:\s+(?:tab|page|screen|view|section|please|thanks|now|today))+$/i, "")
    .replace(/\s+/g, " ")
    .trim();
}

// All alias entries: [{phrase, page, filter}]
function aliasEntries() {
  const out = [];
  const pages = NAV_DATA.pages || {};
  for (const item of NAV_ITEMS) {
    const entry = pages[item.id];
    if (!entry || typeof entry.aliases !== "object") continue;
    for (const [phrase, filter] of Object.entries(entry.aliases)) {
      out.push({ phrase: norm(phrase), page: item.id, filter: filter || null });
    }
  }
  // Longest phrase first so "progress tracker" beats "plans".
  out.sort((a, b) => b.phrase.length - a.phrase.length);
  return out;
}

function inBounds(hay, needle) {
  if (!needle) return false;
  const idx = hay.indexOf(needle);
  if (idx === -1) return false;
  const before = idx === 0 || hay[idx - 1] === " ";
  const afterIdx = idx + needle.length;
  const after = afterIdx === hay.length || hay[afterIdx] === " ";
  return before && after;
}

/**
 * Resolve a natural phrase to {page, filter} (filter may be null).
 * Returns null when no known page alias matches.
 * Order: exact alias, word-boundary partial, then fuzzy near-miss (STT
 * typos like "ordas tab" / "orders tub"). Fuzzy accepts ONLY a clear
 * winner: best normalized score <= 0.34 and clearly ahead of the best
 * hit on any OTHER page (margin >= 0.05). Anything else is null so the
 * caller asks (at most three options) or refuses instead of guessing.
 */
export function resolvePageName(text) {
  const full = norm(text);
  if (!full) return null;
  const candidates = stateCandidates(full);
  const entries = aliasEntries();
  for (const cand of candidates) {
    const exact = entries.find((e) => e.phrase === cand);
    if (exact) return { page: exact.page, filter: exact.filter };
  }
  for (const cand of candidates) {
    const partial = entries.find((e) => inBounds(cand, e.phrase));
    if (partial) return { page: partial.page, filter: partial.filter };
  }
  for (const cand of candidates) {
    const fuzzy = fuzzyWinner(cand, entries);
    if (fuzzy) return { page: fuzzy.page, filter: fuzzy.filter };
  }
  return null;
}

/**
 * Strict gate used by the text assistant: only treat typed text as a
 * navigation command when it starts with a navigation verb or is exactly a
 * known alias (so "what's happening in production?" still goes to the AI).
 */
export function parseNavigationRequest(text) {
  const full = norm(text);
  if (!full) return null;
  const lead = stripLead(full);
  if (lead.hadVerb) return resolvePageName(text);
  // No verb: only an exact full-phrase alias counts (e.g. typing "machines").
  const trail = stripTrail(full);
  const hit = aliasEntries().find((e) => e.phrase === full || e.phrase === trail);
  return hit ? { page: hit.page, filter: hit.filter } : null;
}

// At most three closest page names for the spoken unknown-page answer.
export function unknownPageMessage(text) {
  const want = norm(text);
  // Quote the words without the leading verb ("open the banana page" ->
  // "banana page").
  const raw = stripLead(want).text || want || String(text || "").trim();
  const scored = NAV_ITEMS.map((n) => ({ label: n.label, d: editDistance(want, norm(n.label)) }));
  scored.sort((a, b) => a.d - b.d || a.label.localeCompare(b.label));
  const three = scored.slice(0, 3).map((s) => s.label);
  return `I don't have a page called ${raw}; I can open: ${three.join(", ")}.`;
}

// Suggest the top three page labels closest to free text (ambiguous
// near-miss answers reuse the same cap: never more than three options).
export function suggestPages(text, n = 3) {
  const want = norm(text);
  const scored = NAV_ITEMS.map((item) => {
    const aliases = Object.keys((NAV_DATA.pages || {})[item.id]?.aliases || { [item.label]: null });
    let best = Infinity;
    for (const a of aliases) {
      const s = fuzzyScore(want, norm(a));
      if (s < best) best = s;
    }
    return { label: item.label, id: item.id, s: best };
  });
  scored.sort((a, b) => a.s - b.s || a.label.localeCompare(b.label));
  return scored.slice(0, Math.max(1, Math.min(3, n)));
}

function noSpace(s) {
  return String(s || "").replace(/[^a-z0-9]/g, "");
}

// Phonetic-ish skeleton: drop spaces, collapse doubles, drop vowels after
// the first letter ("orders tub" and "orders tab" share one skeleton).
function skeleton(s) {
  const n = noSpace(s);
  if (!n) return n;
  const collapsed = n.replace(/(.)\1+/g, "$1");
  return collapsed[0] + collapsed.slice(1).replace(/[aeiou]/g, "");
}

// Normalized (0..1+) distance over raw, spaceless and skeleton forms.
export function fuzzyScore(a, b) {
  const x = String(a || "");
  const y = String(b || "");
  const d1 = editDistance(x, y) / Math.max(x.length, y.length, 1);
  const nx = noSpace(x);
  const ny = noSpace(y);
  const d2 = editDistance(nx, ny) / Math.max(nx.length, ny.length, 1);
  const sx = skeleton(x);
  const sy = skeleton(y);
  const d3 = (editDistance(sx, sy) / Math.max(sx.length, sy.length, 1)) * 0.9;
  return Math.min(d1, d2, d3);
}

const FUZZY_ACCEPT = 0.34;
const FUZZY_MARGIN = 0.05;

function fuzzyWinner(cand, entries) {
  const target = stripTrail(cand);
  if (!target) return null;
  let best = null;
  let bestSecond = Infinity;
  const byPage = new Map();
  for (const e of entries) {
    const s = fuzzyScore(target, e.phrase);
    if (!byPage.has(e.page) || s < byPage.get(e.page).s) {
      byPage.set(e.page, { s, entry: e });
    }
    if (!best || s < best.s) {
      if (best) bestSecond = Math.min(bestSecond, best.s);
      best = { s, entry: e };
    } else if (s < bestSecond) {
      bestSecond = s;
    }
  }
  if (!best || best.s > FUZZY_ACCEPT) return null;
  // Margin is measured against the best hit on any OTHER page.
  let otherBest = Infinity;
  for (const [pid, v] of byPage) {
    if (pid !== best.entry.page && v.s < otherBest) otherBest = v.s;
  }
  if (otherBest - best.s < FUZZY_MARGIN) return null;
  return { page: best.entry.page, filter: best.entry.filter };
}

function editDistance(a, b) {
  const m = a.length;
  const n = b.length;
  if (!m) return n;
  if (!n) return m;
  let prev = Array.from({ length: n + 1 }, (_, j) => j);
  for (let i = 1; i <= m; i += 1) {
    const cur = [i];
    for (let j = 1; j <= n; j += 1) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
    prev = cur;
  }
  return prev[n];
}

// Canonical filter values allowed on a page (from shared/navigation.json).
export function allowedFilters(pageId) {
  const f = (NAV_DATA.page_filters || {})[pageId];
  return f && typeof f === "object" ? Object.keys(f) : [];
}

function filterSpeak(pageId, key) {
  const f = (NAV_DATA.page_filters || {})[pageId];
  return f && f[key] ? String(f[key].speak || key) : key;
}

// ---------------------------------------------------------------------------
// Validator
// ---------------------------------------------------------------------------

export function validateUiCommand(raw) {
  let msg;
  try {
    msg = typeof raw === "string" ? JSON.parse(raw) : raw;
  } catch {
    return { ok: false, error: "rejected: not JSON" };
  }
  if (!msg || typeof msg !== "object" || Array.isArray(msg)) {
    return { ok: false, error: "rejected: not an object" };
  }
  const { action } = msg;
  if (!ACTIONS.includes(action)) {
    return { ok: false, error: `rejected: unknown action '${String(action)}'` };
  }
  // Strict shape: no extra top-level fields for this action.
  const allowedKeys = new Set(["action", ...ACTION_FIELDS[action]]);
  for (const key of Object.keys(msg)) {
    if (!allowedKeys.has(key)) {
      return { ok: false, error: `rejected: unexpected field '${String(key)}'` };
    }
  }
  // Every provided string must be a plain, safe, bounded value.
  for (const key of ACTION_FIELDS[action]) {
    if (key in msg && msg[key] !== undefined && msg[key] !== null) {
      if (typeof msg[key] !== "string") {
        return { ok: false, error: `rejected: ${key} must be a string` };
      }
      if (looksUnsafe(msg[key])) {
        return { ok: false, error: `rejected: ${key} must not be a URL or code` };
      }
      if (msg[key].length > MAX_LEN) {
        return { ok: false, error: `rejected: ${key} too long` };
      }
    }
  }

  const args = {};
  if (action === "navigate") {
    if (!isNonEmptyString(msg.page)) return { ok: false, error: "rejected: navigate needs page" };
    const page = msg.page.trim();
    if (!navIds().has(page)) return { ok: false, error: `rejected: ${unknownPageMessage(page)}` };
    args.page = page;
    if ("filter" in msg) {
      if (!isNonEmptyString(msg.filter)) {
        return { ok: false, error: "rejected: filter must be a non-empty string" };
      }
      const filter = msg.filter.trim();
      const okFilters = allowedFilters(page);
      if (!okFilters.includes(filter)) {
        const speaks = okFilters.map((k) => filterSpeak(page, k));
        return {
          ok: false,
          error: speaks.length
            ? `rejected: ${labelOf(page)} has no filter '${filter}'; I can show: ${speaks.join(", ")}.`
            : `rejected: ${labelOf(page)} has no voice filters.`,
        };
      }
      args.filter = filter;
    }
  } else if (action === "select_machine") {
    if (!isNonEmptyString(msg.machine)) return { ok: false, error: "rejected: select_machine needs machine" };
    args.machine = msg.machine.trim();
  } else if (action === "open_order") {
    if (!isNonEmptyString(msg.order)) return { ok: false, error: "rejected: open_order needs order" };
    args.order = msg.order.trim();
  } else if (action === "open_incident") {
    if (!isNonEmptyString(msg.incident)) return { ok: false, error: "rejected: open_incident needs incident" };
    args.incident = msg.incident.trim();
  } else if (action === "focus_order_on_map") {
    if (!isNonEmptyString(msg.order)) return { ok: false, error: "rejected: focus_order_on_map needs order" };
    args.order = msg.order.trim();
  }
  // show_proposals takes no args.
  return { ok: true, action, args };
}

export const UI_COMMAND_METHOD = "ui.command";
export const UI_COMMAND_ACTIONS = ACTIONS;
