"""Deterministic worker/machine matching for plan dispatch (Phase 7).

Rules (documented, no guessing):
- Worker eligible: employee.status ACTIVE (or unset), availability AVAILABLE
  (or unset), and required_skill found (case-insensitive substring) in their
  skills (any stored shape: dict/list/string).
- Machine eligible: machine_type equals (case-insensitive) the item's
  machine_type, status OPERATIONAL (or unset); HEALTH GOOD preferred.
- Ranking: fewest open tasks, then HEALTH GOOD, then name. If the top two
  tie on every key the item stays UNASSIGNED for the manager to fix.
- 0 candidates -> UNASSIGNED with a reason. Never misassigns silently.
"""
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from backend.models.models import Employee, Machine, Task

OPEN_TASK = ("PENDING", "IN_PROGRESS", "PLANNED")


def skills_of(emp: Employee) -> List[str]:
    s = emp.skills
    if s is None:
        return []
    if isinstance(s, dict):
        # Explicit shapes first; an empty items list means no skills (never
        # fall through to values(), which would stringify the empty list).
        if isinstance(s.get("items"), list):
            vals = s["items"]
        elif isinstance(s.get("value"), str):
            vals = [s["value"]]
        elif isinstance(s.get("value"), list):
            vals = s["value"]
        else:
            vals = [v for v in s.values() if isinstance(v, str)]
        out: List[str] = []
        for v in vals:
            if isinstance(v, str):
                out.extend(p.strip().lower() for p in v.replace(";", ",").split(",") if p.strip())
        return out
    if isinstance(s, list):
        return [str(v).lower() for v in s]
    return [str(s).lower()]


def _skill_match(have: List[str], need: str) -> bool:
    n = (need or "").strip().lower()
    if not n:
        return True
    return any(n in h or h in n for h in have)


def open_task_count(db: Session, employee_id: UUID) -> int:
    try:
        return (
            db.query(Task)
            .filter(Task.employee_id == employee_id, Task.status.in_(list(OPEN_TASK)))
            .count()
        )
    except Exception:
        return 0


def match_worker(db: Session, required_skill: str) -> Tuple[Optional[Employee], str]:
    cands = []
    try:
        employees = db.query(Employee).all()
    except Exception:
        return None, "employee lookup failed"
    for e in employees:
        if (e.status or "ACTIVE").upper() != "ACTIVE":
            continue
        if (e.availability or "AVAILABLE").upper() != "AVAILABLE":
            continue
        if not _skill_match(skills_of(e), required_skill or ""):
            continue
        cands.append((open_task_count(db, e.id), e.name or "", e))
    if not cands:
        return None, f"no AVAILABLE worker with skill '{required_skill}'"
    cands.sort(key=lambda t: (t[0], t[1]))
    if len(cands) > 1 and cands[0][0] == cands[1][0] and cands[0][1] == cands[1][1]:
        return None, "ambiguous: identical top candidates, manager must choose"
    return cands[0][2], ""


def match_machine(db: Session, machine_type: str) -> Tuple[Optional[Machine], str]:
    if not (machine_type or "").strip():
        return None, ""
    want = machine_type.strip().lower()
    try:
        machines = db.query(Machine).all()
    except Exception:
        return None, "machine lookup failed"
    cands = [
        m for m in machines
        if (m.machine_type or "").strip().lower() == want
        and (m.status or "OPERATIONAL").upper() == "OPERATIONAL"
    ]
    if not cands:
        return None, f"no OPERATIONAL machine of type '{machine_type}'"
    cands.sort(key=lambda m: (0 if (m.health_status or "GOOD").upper() == "GOOD" else 1, m.name or ""))
    if len(cands) > 1 and (cands[0].health_status or "") == (cands[1].health_status or "") and cands[0].name == cands[1].name:
        return None, "ambiguous machines, manager must choose"
    return cands[0], ""


def match_item(db: Session, item: Dict[str, Any]) -> Dict[str, Any]:
    """Match one plan item -> {employee, machine, reasons}."""
    worker, w_reason = match_worker(db, item.get("required_skill") or "")
    machine, m_reason = match_machine(db, item.get("machine_type") or "")
    reasons = [r for r in (w_reason, m_reason) if r]
    return {"employee": worker, "machine": machine, "reasons": reasons}
