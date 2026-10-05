"""Shared page-alias resolution for Jarvis.

Reads shared/navigation.json — the SAME file the browser validator
(frontend/src/components/voice/uiCommand.js) uses — so there is exactly one
place where alias and filter rules live. The page-id list must always match
frontend/src/config/nav.js; the browser re-validates every navigate target
against nav.js, so an out-of-sync id can never change the screen.
"""
from __future__ import annotations

import json
import os
import re

_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "shared", "navigation.json"
)

with open(_PATH, encoding="utf-8") as _f:
    DATA = json.load(_f)

PAGES: dict = DATA.get("pages") or {}
FILTERS: dict = DATA.get("page_filters") or {}

_LEAD_FILLER = re.compile(
    r"^(?:please|ok|okay|hey|now|just|can you|could you|i want to|i would like to|i'd like to)\s+"
)
_LEAD_VERB = re.compile(
    r"^(?:open|go to|navigate to|navigate|take me to|switch to|jump to|pull up|bring up"
    r"|head to|goto|show me the|show me|show|display|load|bring me to)\b"
)
_TRAIL = re.compile(r"(?:\s+(?:tab|page|screen|view|section|please|thanks|now|today))+$")


def _norm(text) -> str:
    s = str(text or "").lower()
    s = re.sub(r"[.,!?;:'\"()]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _strip_lead(s: str) -> tuple[str, bool]:
    out = s
    had_verb = False
    for _ in range(4):
        before = out
        out = _LEAD_FILLER.sub("", out).strip()
        m = _LEAD_VERB.match(out)
        if m:
            out = out[m.end():]
            had_verb = True
        out = re.sub(r"^[\s:,-]+", "", out)
        out = re.sub(r"^(?:the|my|that)\s+", "", out).strip()
        if out == before:
            break
    return out, had_verb


def _strip_trail(s: str) -> str:
    return re.sub(r"\s+", " ", _TRAIL.sub("", s)).strip()


def _entries() -> list[tuple[str, str, str | None]]:
    out = []
    for pid, entry in PAGES.items():
        aliases = entry.get("aliases") or {}
        for phrase, flt in aliases.items():
            out.append((_norm(phrase), pid, flt or None))
    out.sort(key=lambda e: -len(e[0]))
    return out


def _in_bounds(hay: str, needle: str) -> bool:
    if not needle:
        return False
    idx = hay.find(needle)
    if idx == -1:
        return False
    before = idx == 0 or hay[idx - 1] == " "
    after = idx + len(needle)
    return before and (after == len(hay) or hay[after] == " ")


def _state_candidates(s: str) -> list[str]:
    """Every intermediate form after each strip step, so an exact alias like
    'open incidents' matches BEFORE 'open' is stripped as a verb."""
    out: list[str] = []

    def push(t: str) -> None:
        if not t:
            return
        t2 = _strip_trail(t)
        if t not in out:
            out.append(t)
        if t2 and t2 != t and t2 not in out:
            out.append(t2)

    cur = s
    push(cur)
    for _ in range(4):
        before = cur
        cur = _LEAD_FILLER.sub("", cur).strip()
        m = _LEAD_VERB.match(cur)
        if m:
            cur = cur[m.end():]
        cur = re.sub(r"^[\s:,-]+", "", cur)
        cur = re.sub(r"^(?:the|my|that)\s+", "", cur).strip()
        if cur == before:
            break
        push(cur)
    return out


def resolve_page(text) -> tuple[str, str, str | None] | None:
    """Natural phrase -> (page_id, label, alias_filter|None). None = unknown.

    Order: exact alias, word-boundary partial, then fuzzy near-miss (STT
    typos like "ordas tab"). Fuzzy accepts ONLY a clear winner (best
    normalized score <= 0.34 and >= 0.05 ahead of the best hit on any
    other page). Anything else is None so the caller asks (<=3 options)
    or refuses instead of guessing.
    """
    full = _norm(text)
    if not full:
        return None
    candidates = _state_candidates(full)
    entries = _entries()
    for cand in candidates:
        for phrase, pid, flt in entries:
            if phrase == cand:
                return pid, (PAGES[pid].get("label") or pid), flt
    for cand in candidates:
        for phrase, pid, flt in entries:
            if _in_bounds(cand, phrase):
                return pid, (PAGES[pid].get("label") or pid), flt
    for cand in candidates:
        hit = _fuzzy_winner(cand, entries)
        if hit is not None:
            pid, flt = hit
            return pid, (PAGES[pid].get("label") or pid), flt
    return None


def resolve_filter(page_id: str, text) -> str | None:
    """Natural filter words -> canonical filter key for that page (None = no)."""
    table = FILTERS.get(page_id) or {}
    if not table:
        return None
    t = _norm(text)
    if not t:
        return None
    for key, meta in table.items():
        meta = meta or {}
        if t == _norm(key) or t == _norm(meta.get("speak") or ""):
            return key
        for a in meta.get("aliases") or []:
            if t == _norm(a):
                return key
    for key, meta in table.items():  # word-boundary containment ("show open only")
        for a in (meta or {}).get("aliases") or []:
            if _in_bounds(t, _norm(a)):
                return key
    return None


def filter_speak(page_id: str, key: str) -> str:
    meta = (FILTERS.get(page_id) or {}).get(key) or {}
    return str(meta.get("speak") or key)


def filter_speak_list(page_id: str) -> list[str]:
    return [filter_speak(page_id, k) for k in (FILTERS.get(page_id) or {})]


def page_labels() -> list[str]:
    return [e.get("label") or pid for pid, e in PAGES.items()]


def label_of(page_id: str) -> str:
    return (PAGES.get(page_id) or {}).get("label") or page_id


def _edit_distance(a: str, b: str) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def unknown_page_message(text) -> str:
    """Spoken answer for an unknown page, listing at most three names."""
    want = _norm(text)
    # Quote the admin's words without the leading verb ("open the banana
    # page" -> "banana page").
    raw = _strip_lead(want)[0] or str(text or "").strip() or "?"
    scored = sorted(
        (_edit_distance(want, _norm(lbl)), lbl) for lbl in page_labels()
    )
    three = [lbl for _, lbl in scored[:3]]
    return f"I don't have a page called {raw}; I can open: {', '.join(three)}."


def _no_space(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s or "")


def _skeleton(s: str) -> str:
    n = _no_space(s)
    if not n:
        return n
    collapsed = re.sub(r"(.)\1+", r"\1", n)
    return collapsed[0] + re.sub(r"[aeiou]", "", collapsed[1:])


def fuzzy_score(a: str, b: str) -> float:
    """Normalized (0..1+) distance over raw, spaceless, skeleton forms."""
    x, y = str(a or ""), str(b or "")
    d1 = _edit_distance(x, y) / max(len(x), len(y), 1)
    nx, ny = _no_space(x), _no_space(y)
    d2 = _edit_distance(nx, ny) / max(len(nx), len(ny), 1)
    sx, sy = _skeleton(x), _skeleton(y)
    d3 = (_edit_distance(sx, sy) / max(len(sx), len(sy), 1)) * 0.9
    return min(d1, d2, d3)


_FUZZY_ACCEPT = 0.34
_FUZZY_MARGIN = 0.05


def _fuzzy_winner(cand: str, entries) -> tuple[str, str | None] | None:
    target = _strip_trail(cand)
    if not target:
        return None
    best = None  # (score, pid, flt)
    best_second = float("inf")
    by_page: dict[str, float] = {}
    for phrase, pid, flt in entries:
        s = fuzzy_score(target, phrase)
        if pid not in by_page or s < by_page[pid]:
            by_page[pid] = s
        if best is None or s < best[0]:
            if best is not None:
                best_second = min(best_second, best[0])
            best = (s, pid, flt)
        elif s < best_second:
            best_second = s
    if best is None or best[0] > _FUZZY_ACCEPT:
        return None
    other_best = min((s for pid, s in by_page.items() if pid != best[1]),
                     default=float("inf"))
    if other_best - best[0] < _FUZZY_MARGIN:
        return None
    return best[1], best[2]


def suggest_pages(text, n: int = 3) -> list[str]:
    """Top (at most three) page labels closest to free text."""
    want = _norm(text)
    scored = []
    for pid, entry in PAGES.items():
        aliases = list((entry.get("aliases") or {}).keys()) or [pid]
        best = min((fuzzy_score(want, _norm(a)) for a in aliases),
                   default=float("inf"))
        scored.append((best, entry.get("label") or pid))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [lbl for _, lbl in scored[: max(1, min(3, n))]]
