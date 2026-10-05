"""Deterministic pre-LLM turn router for Jarvis.

Pure, synchronous routing (text -> action) plus one small async executor that
calls the EXISTING tools directly — no LLM call, so navigation/undo/goodbye
keep working (and speaking) even when the language model is down.

Rules (shared with the browser typed gate in
frontend/src/components/voice/uiCommand.js):
- navigation only on a leading nav verb OR a bare exact page alias
  ("which machines need attention?" has no verb -> NOT navigation -> LLM).
- "employee tab/list/staff" always means the Employees list page (exact
  aliases in shared/navigation.json).
- compound phrases (machine codes, incidents, filters, proposals, order
  numbers) go through the existing filter/compound handling in tools.
- ambiguous/unknown WITH a verb -> the tool's own <=3-option sentence.
- "undo that" -> undo_last; explicit end phrases -> end_session.
- anything else -> None (the normal LLM path).

Timeouts: quick local resolve; tool calls are bounded by the caller.
"""
from __future__ import annotations

import asyncio
import re
import time

try:
    from . import navigation as nav
except ImportError:  # loaded as a top-level script (tests, direct runs)
    import navigation as nav

NAV_VERBS = (
    "open", "go to", "navigate to", "navigate", "take me to", "switch to",
    "jump to", "pull up", "bring up", "head to", "goto", "show me the",
    "show me", "show", "display", "load", "bring me to",
)

_VERB_RE = re.compile(
    r"^(?:please\s+|ok(?:ay)?\s+|hey\s+|now\s+|just\s+)?"
    r"(?:open|go to|navigate to|navigate|take me to|switch to|jump to|"
    r"pull up|bring up|head to|goto|show me the|show me|show|display|load|"
    r"bring me to)\b[\s:,]*",
)

_END_RES = [
    r"^(goodbye|bye)( jarvis)?$",
    r"^end (the )?session$",
    r"^end voice$",
    r"^stop listening$",
    r"^disconnect( jarvis| the session| voice)?$",
    r"^quit( listening)?$",
]

_UNDO_RE = re.compile(
    r"^(?:please\s+)?(?:undo|cancel|revert)"
    r"(?:\s+(?:that|this|it|the last(?: one| command)?|last))?\s*[.?!]*$"
)

_MACHINE_RE = re.compile(r"\bm[-\s]*0*(\d{1,3})\b")
_MACHINE_WORDS = {
    "zero": "0", "o": "0", "oh": "0",
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9",
}
_MACHINE_SPOKEN_RE = re.compile(r"\bm\s+((?:zero|o|oh|one|two|three|four|five|six|seven|eight|nine)[\s-]+){1,4}(?:zero|o|oh|one|two|three|four|five|six|seven|eight|nine)\b")
_ORDER_RE = re.compile(r"\bord[-\s]*(\d+)\b")
_EMP_RE = re.compile(r"\bemp[-\s]*0*(\d+)\b")

# Data-question guard: with these present the user wants an ANSWER from live
# data (LLM + read tools), not a screen open. "?" or question/data words.
# ("report" is deliberately absent: "open the weekly report" is navigation.)
_DATA_RE = re.compile(
    r"\?|\b(what|which|how|why|when|who|whom|whose|many|much|status|health|"
    r"temperature|vibration|telemetry|readings?|workload|available|attention|"
    r"late|risk|summary|tell|explain)\b"
)

# Fragment merge: join two user turns within this window when the first is a
# short fragment. Added latency: one extra pure-function resolve (~0ms).
MERGE_WINDOW_S = 1.5
_MERGE_PREV_WORDS = 4


def _norm(text: str) -> str:
    return nav._norm(text)


def _strip_verb(text: str) -> tuple[str, bool]:
    t = _norm(text)
    m = _VERB_RE.match(t)
    if not m:
        return t, False
    rest = t[m.end():].strip()
    rest = re.sub(r"^(?:the|my|that)\s+", "", rest).strip()
    return rest, True


def _exact_aliases() -> dict[str, tuple[str, str | None]]:
    out: dict[str, tuple[str, str | None]] = {}
    for pid, entry in nav.PAGES.items():
        for phrase, flt in (entry.get("aliases") or {}).items():
            out.setdefault(_norm(phrase), (pid, flt or None))
    return out


_EXACT: dict[str, tuple[str, str | None]] | None = None


def _exact_alias(text: str) -> tuple[str, str | None] | None:
    global _EXACT
    if _EXACT is None:
        _EXACT = _exact_aliases()
    hit = _EXACT.get(_norm(text))
    if hit is None:
        hit = _EXACT.get(nav._strip_trail(_norm(text)))
    return hit


_GREETING_RE = re.compile(r"^(hello|hey|hi|yo|good (morning|afternoon|evening))\s+(jarvis|voice)\s*[.?!]*$")


def _bare_page(text: str) -> tuple[str, str | None] | None:
    """Bare page name without a verb: exact alias or a CLEAR fuzzy winner
    (same margin rule as the shared resolver). Greetings ("hello jarvis")
    are never navigation."""
    t = _norm(text)
    if _GREETING_RE.match(t):
        return None
    hit = _exact_alias(text)
    if hit is not None:
        return hit
    try:
        entries = nav._entries()
        for cand in (t, nav._strip_trail(t)):
            if not cand:
                continue
            won = nav._fuzzy_winner(cand, entries)
            if won is not None:
                return won
    except Exception:
        return None
    return None


def is_end_request(text: str) -> bool:
    t = _norm(text).strip()
    t = re.sub(r"\s*[.?!]*$", "", t)
    return any(re.match(p, t) for p in _END_RES)


def is_undo_request(text: str) -> bool:
    return _UNDO_RE.match(_norm(text).strip()) is not None


def is_navigation_request(text: str) -> bool:
    """Verb-gated like the typed gate: verb OR bare page name only."""
    rest, had_verb = _strip_verb(text)
    if had_verb:
        return True
    return _bare_page(text) is not None


def _machine_code(text: str) -> str | None:
    t = _norm(text)
    m = _MACHINE_RE.search(t)
    if m:
        return f"M-{int(m.group(1)):03d}"
    m = _MACHINE_SPOKEN_RE.search(t)
    if m:
        digits = "".join(_MACHINE_WORDS.get(w, "") for w in re.findall(r"[a-z]+", m.group(0))[1:])
        if digits:
            return f"M-{int(digits):03d}"
    return None


def _order_number(text: str) -> str | None:
    m = _ORDER_RE.search(_norm(text))
    # Keep digits exactly as spoken (ORD-004 is not ORD-4).
    return f"ORD-{m.group(1)}" if m else None


def classify_compound(text: str) -> dict | None:
    """Compound screen needs -> navigate_ui kwargs (no LLM needed).

    Data questions ("show me the STATUS of M-001?", "what is ORD-004
    worth?") are NOT compounds — they fall through to the LLM, which
    answers from live data.
    """
    t = _norm(text)
    if _DATA_RE.search(t):
        return None
    machine = _machine_code(text)
    order = _order_number(text)
    has_incident = bool(re.search(r"\bincidents?\b", t))
    if machine and has_incident:
        return {"action": "open_incident", "incident": machine}
    if machine and re.search(r"\b(map|telemetry|sensor|temperature|vibration|status|health|reading)\b", t):
        return {"action": "select_machine", "machine": machine}
    if machine:
        return {"action": "select_machine", "machine": machine}
    if order and re.search(r"\bmap\b", t):
        return {"action": "focus_order_on_map", "order": order}
    if order:
        return {"action": "open_order", "order": order}
    if re.search(r"\bproposals?\b.*\b(pending|waiting)\b|\bpending\b.*\bproposals?\b|\bpending proposals\b", t):
        return {"action": "show_proposals"}
    if re.search(r"\b(emp[-\s]*\d+|that (worker|employee|person)|workload|who is (free|available))\b", t):
        return None  # workforce questions need data -> LLM
    filt_incidents = nav.resolve_filter("incidents", t)
    if has_incident and filt_incidents:
        return {"action": "navigate", "page": "incidents", "filter": filt_incidents}
    if has_incident:
        return {"action": "navigate", "page": "incidents"}
    return None


def route_turn(text: str) -> dict | None:
    """Pure classification: returns navigate_ui kwargs / end / undo, or None.

    Return shapes:
      {"kind": "end"} | {"kind": "undo"} |
      {"kind": "tool", "kwargs": {...navigate_ui kwargs...}} |
      None (let the LLM handle it)
    """
    t = _norm(text)
    if not t:
        return None
    if is_end_request(text):
        return {"kind": "end"}
    if is_undo_request(text):
        return {"kind": "undo"}
    compound = classify_compound(text)
    if compound is not None:
        return {"kind": "tool", "kwargs": compound}
    rest, had_verb = _strip_verb(text)
    if had_verb:
        if not rest:
            return {"kind": "tool", "kwargs": {"action": "navigate", "page": ""}}
        # A resolvable page always wins ("open what if" despite "what").
        # Data questions that resolve to nothing ("show me the status of
        # M-001") fall through to the LLM; anything else gets the tool's
        # own short answer (including the <=3-option unknown sentence).
        if _bare_page(rest) is not None or not _DATA_RE.search(rest):
            return {"kind": "tool", "kwargs": {"action": "navigate", "page": rest}}
        return None
    if _bare_page(text) is not None:
        return {"kind": "tool", "kwargs": {"action": "navigate", "page": t}}
    return None


def should_merge(prev_text: str, prev_time: float, cur_text: str, now: float | None = None) -> str | None:
    """Join a short fragment with the next turn inside the merge window."""
    if not prev_text or not cur_text:
        return None
    if (now if now is not None else time.monotonic()) - prev_time > MERGE_WINDOW_S:
        return None
    if len(_norm(prev_text).split()) > _MERGE_PREV_WORDS:
        return None
    combined = f"{prev_text.strip()} {cur_text.strip()}"
    # Only merge when the combination routes but the current turn alone
    # would fall through to the LLM.
    if route_turn(cur_text) is None and route_turn(combined) is not None:
        return combined
    return None


async def execute_route(route: dict, tools_by_name: dict, timeout_s: float = 6.0):
    """Run a routed action against the EXISTING tools. Always returns a
    short speakable sentence (never None, never raises)."""
    kind = route.get("kind")
    try:
        if kind == "end":
            fn = tools_by_name.get("end_session")
            if fn is None:
                return "Okay, ending the session."
            return await asyncio.wait_for(fn(None), timeout=timeout_s) or "Okay, ending the session."
        if kind == "undo":
            fn = tools_by_name.get("undo_last")
            if fn is None:
                return "There is nothing recent to undo."
            return await asyncio.wait_for(fn(None), timeout=timeout_s) or "Undone."
        if kind == "tool":
            fn = tools_by_name.get("navigate_ui")
            if fn is None:
                return "The screen could not be updated right now."
            kwargs = dict(route.get("kwargs") or {})
            kwargs.setdefault("action", "navigate")
            res = await asyncio.wait_for(fn(None, **kwargs), timeout=timeout_s)
            return (res or "Shown on the admin screen.")[:300]
    except (asyncio.TimeoutError, TimeoutError):
        if kind == "tool":
            return "The screen took too long to answer. Please say it again."
        return "Sorry, that took too long. Please say it again."
    except Exception as e:
        # Log type only (no secrets); always end with speech.
        try:
            import logging as _logging
            _logging.getLogger("jarvis.router").warning("route failed: %s", type(e).__name__)
        except Exception:
            pass
        if kind == "tool":
            return "The screen could not be updated right now."
        return "Sorry, that took too long. Please say it again."
    return "Sorry, that took too long. Please say it again."
