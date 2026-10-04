"""FAST command policy (Tier 1/2/3) + smart defaults.

ONE module holding every rule for direct voice/text command execution,
covered by unit tests. No LLM in here — pure deterministic policy.

Tier 1: execute immediately on a clear command.
Tier 2: needs one spoken yes/no; in autopilot ("make anything by yourself")
    pick the documented safe alternative and state it.
Tier 3: never by voice/text (no execution path exists); Jarvis names the
    on-screen place instead.
"""
import re
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

UNDO_MINUTES = 15
DUPLICATE_SECONDS = 60
TIER2_MAX_AFFECTED = 5
AUTOPILOT_MAX_AFFECTED = 10

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

# Tier 3: intent patterns that must never execute via commands.
FORBIDDEN = [
    (r"\bdelete\b|\bremove\b|\bdestroy\b|\bdrop\b|\bclear all\b", "delete"),
    (r"\bpassword\b|\bcredential\b|\blogin\b|\btoken\b|\bsecret\b|\bapi key\b|\bapikey\b", "credentials"),
    (r"\bavailability\b.*\b(for|of)\b|\bmark\b.*\b(on.?leave|off duty)\b", "availability"),
    (r"\bthresholds?\b|\bfactory profile\b|\bprofile setting\b", "profile"),
]

PRIORITY_WORDS = {"urgent": "URGENT", "high": "HIGH", "low": "LOW"}


def is_forbidden(text: str):
    """(True, reason) if the wording asks for a Tier 3 action."""
    t = (text or "").lower()
    for pat, reason in FORBIDDEN:
        if re.search(pat, t):
            return True, reason
    return False, ""


def refusal_for(reason: str) -> str:
    where = {
        "delete": "delete it on the Tasks or Orders screen",
        "credentials": "manage logins on the Employees page",
        "availability": "change availability on the Employees page",
        "profile": "change that in Factory Profile",
    }
    return f"I cannot do that by voice — {where.get(reason, 'do that on screen')}."


def parse_priority(text: str) -> str:
    t = (text or "").lower()
    for word, prio in PRIORITY_WORDS.items():
        if re.search(rf"\b{word}\b", t):
            return prio
    return "NORMAL"


def _at_ist(day, hour: int, minute: int = 0):
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST)


def parse_deadline(text, now=None):
    """Natural deadline -> tz-aware datetime. Default: tomorrow 18:00 IST.
    Understands ISO strings, "tonight", "tomorrow" (+hour phrases),
    weekday names ("by Friday"), "in N days/weeks". Returns None only if
    text is empty AND no default wanted (never here — default always)."""
    now = now or datetime.now(IST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=IST)
    t = (text or "").strip()
    if t:
        try:
            dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=IST)
        except (ValueError, TypeError):
            pass
    low = t.lower()
    if re.search(r"\btonight\b", low):
        dl = _at_ist(now.date(), 21, 0)
        return dl if dl > now else dl + timedelta(days=1)
    hour = 18
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", low)
    if m:
        h = int(m.group(1)) % 12 + (12 if m.group(3) == "pm" else 0)
        hour = h
        minute = int(m.group(2) or 0)
    elif re.search(r"\bmorning\b", low):
        hour, minute = 9, 0
    elif re.search(r"\b(evening|eod|end of day)\b", low):
        hour, minute = 18, 0
    else:
        minute = 0
    m = re.search(r"\bin\s+(\d+)\s+(day|days|week|weeks)\b", low)
    if m:
        days = int(m.group(1)) * (7 if "week" in m.group(2) else 1)
        return _at_ist(now.date() + timedelta(days=days), hour, minute)
    for name, wd in WEEKDAYS.items():
        if re.search(rf"\b{name}\b", low):
            delta = (wd - now.weekday()) % 7
            dl = _at_ist(now.date() + timedelta(days=delta), hour, minute)
            if dl <= now:
                dl += timedelta(days=7)
            return dl
    if re.search(r"\btomorrow\b", low) or not t:
        return _at_ist(now.date() + timedelta(days=1), hour, minute)
    # Unknown phrasing: still return the default rather than blocking.
    return _at_ist(now.date() + timedelta(days=1), 18, 0)


def speak_due(dt) -> str:
    """'tomorrow 6 PM' style label relative to now (Asia/Kolkata)."""
    if dt is None:
        return "no due date"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    local = dt.astimezone(IST)
    now = datetime.now(IST)
    day = "today" if local.date() == now.date() else (
        "tomorrow" if local.date() == now.date() + timedelta(days=1) else
        local.strftime("%A"))
    h = local.hour % 12 or 12
    return f"{day} {h} {local.strftime('%p')}"


def match_skill(text: str, skills: list) -> str | None:
    """Longest profile skill appearing in the wording (case-insensitive)."""
    t = (text or "").lower()
    best = None
    for s in skills or []:
        name = s if isinstance(s, str) else str(s.get("name") or s.get("skill") or "")
        if name and name.lower() in t and (best is None or len(name) > len(best)):
            best = name
    return best


def task_name_from(text: str) -> str:
    """'CNC operation task' -> 'CNC operation' (strip trailing task-words)."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.sub(r"\s+(task|job|work|activity)s?$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"^(a|an|the|new|another)\s+", "", t, flags=re.IGNORECASE)
    return (t or "General task")[:255]


def next_order_number(existing: list) -> str:
    """ORD-001 style: one above the highest numeric ORD- suffix in use."""
    best = 0
    for n in existing or []:
        m = re.fullmatch(r"ORD-(\d+)", str(n or "").strip().upper())
        if m:
            best = max(best, int(m.group(1)))
    return f"ORD-{best + 1:03d}"
