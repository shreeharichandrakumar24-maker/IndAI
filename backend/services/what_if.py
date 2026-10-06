"""Natural-language what-if simulation: ONE employee OR ONE machine briefly unavailable.

READ-ONLY by construction: every function here only SELECTs and builds
plain-Python result dicts. No attribute is ever set on an ORM object, no
row is added or deleted, and the endpoint commits nothing — the real
database is identical before and after a simulation.

Two scenario types only: EMPLOYEE_LEAVE and MACHINE_UNAVAILABLE.
All queries use the caller's scoped session, so Factory B rows never leak
into Factory A's simulation (unknown/other-factory names read as unknown).
"""
import re
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from backend.models.models import Employee, Machine, Order, ProductionRun, Task

CLOSED_TASK_STATUSES = frozenset({"DONE", "COMPLETED", "CANCELLED"})
FINISHED_RUN_STATUSES = frozenset({"COMPLETED", "DONE"})
ACTIVE_RUN_STATUSES = frozenset({"IN_PROGRESS", "RUNNING"})


class WhatIfError(Exception):
    """User-facing simulation failure (clarification, not a crash)."""

    def __init__(self, detail: str, status_code: int = 422):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _norm(status) -> str:
    return (status or "").strip().upper()


# --------------------------------------------------------------------------
# Scenario parsing (deterministic; the LLM is only ever used for narrative)
# --------------------------------------------------------------------------

_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|days?)\b", re.IGNORECASE)
_TIME_RANGE_RE = re.compile(
    r"from\s+(\d+(?:\.\d+)?)\s*(am|pm)\s+to\s+(\d+(?:\.\d+)?)\s*(am|pm)\b", re.IGNORECASE
)
_CODE_RE = re.compile(r"\b([A-Za-z]+-?\d+)\b")
_QUOTED_RE = re.compile(r'"([^"]+)"|\'([^\']+)\'')

_EMPLOYEE_HINTS = ("leave", "absent", "absence", "vacation", "sick", "time off", "day off",
                   "on leave", "takes leave", "take leave", "leave for", "absent for")
_MACHINE_HINTS = ("machine", "maintenance", "down", "breakdown", "rest", "repair", "out of order",
                  "breaks down", "shut down", "shutdown")


def _to_24h(hour: float, meridiem: str) -> float:
    meridiem = meridiem.lower()
    if meridiem == "am":
        return 0.0 if hour == 12 else hour
    return hour if hour == 12 else hour + 12


def _parse_duration_hours(text: str) -> Optional[float]:
    m = _TIME_RANGE_RE.search(text)
    if m:
        start = _to_24h(float(m.group(1)), m.group(2))
        end = _to_24h(float(m.group(3)), m.group(4))
        span = (end - start) % 24
        return round(span, 2) if span > 0 else None
    m = _DURATION_RE.search(text)
    if m:
        value = float(m.group(1))
        return round(value * 24, 2) if m.group(2).lower().startswith("day") else round(value, 2)
    return None


def _candidate_tokens(text: str) -> List[str]:
    tokens = [t for pair in _QUOTED_RE.findall(text) for t in pair if t]
    tokens += _CODE_RE.findall(text)
    # Capitalized words / phrases (names like "Ravi", "CNC Housing")
    for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b", text):
        tokens.append(m.group(1))
    seen, out = set(), []
    for t in tokens:
        key = t.strip().lower()
        if key and key not in seen and len(key) >= 2:
            seen.add(key)
            out.append(t.strip())
    return out


def _match_employee(employees: List[Employee], token: str) -> List[Employee]:
    key = token.strip().lower()
    exact = [e for e in employees
             if (e.employee_code or "").strip().lower() == key or (e.name or "").strip().lower() == key]
    if exact:
        return exact
    if len(key) >= 3:
        return [e for e in employees if key in (e.name or "").lower()]
    return []


def _match_machine(machines: List[Machine], token: str) -> List[Machine]:
    key = token.strip().lower()
    exact = [m for m in machines
             if (m.machine_code or "").strip().lower() == key or (m.name or "").strip().lower() == key]
    if exact:
        return exact
    if len(key) >= 3:
        return [m for m in machines if key in (m.name or "").lower()]
    return []


def parse_scenario(db: Session, text: str) -> Dict[str, Any]:
    """Normalize free text into {type, employee_id/machine_id, duration_hours, reason}.

    Raises WhatIfError with a clear message instead of guessing when the
    entity is unknown/ambiguous, the scenario is unsupported, or no
    duration was given.
    """
    raw = (text or "").strip()
    if not raw:
        raise WhatIfError("Describe a scenario first, e.g. 'What if Ravi takes leave for 2 days?'")
    lowered = raw.lower()

    employees = db.query(Employee).all()
    machines = db.query(Machine).all()
    emp_hits = {e.id: e for tok in _candidate_tokens(raw) for e in _match_employee(employees, tok)}
    mac_hits = {m.id: m for tok in _candidate_tokens(raw) for m in _match_machine(machines, tok)}

    emp_hint = any(h in lowered for h in _EMPLOYEE_HINTS)
    mac_hint = any(h in lowered for h in _MACHINE_HINTS)
    scenario_type = None
    if emp_hint and not mac_hint:
        scenario_type = "EMPLOYEE_LEAVE"
    elif mac_hint and not emp_hint:
        scenario_type = "MACHINE_UNAVAILABLE"
    elif len(emp_hits) == 1 and not mac_hits:
        scenario_type = "EMPLOYEE_LEAVE"
    elif len(mac_hits) == 1 and not emp_hits:
        scenario_type = "MACHINE_UNAVAILABLE"

    if scenario_type is None:
        if emp_hits and mac_hits:
            raise WhatIfError(
                "That could mean an employee or a machine. "
                "Say 'leave' for a person or 'maintenance/down' for a machine.")
        raise WhatIfError("Currently I can simulate employee leave and machine unavailability.")

    duration = _parse_duration_hours(raw)
    if duration is None:
        raise WhatIfError(
            "Please include a duration, e.g. 'for 2 days', 'for 4 hours', or 'from 10 AM to 5 PM'.")

    if scenario_type == "EMPLOYEE_LEAVE":
        if not emp_hits:
            raise WhatIfError(
                "I couldn't identify the employee from the scenario. "
                "Please provide a clearer name or employee code.")
        if len(emp_hits) > 1:
            names = ", ".join(sorted({e.name for e in emp_hits.values()}))
            raise WhatIfError(
                f"That matches more than one employee ({names}). Please use the full name or code.")
        emp = next(iter(emp_hits.values()))
        return {"type": "EMPLOYEE_LEAVE", "employee_id": emp.id,
                "entity_name": emp.name, "duration_hours": duration, "reason": "leave"}

    if not mac_hits:
        raise WhatIfError(
            "I couldn't identify the machine from the scenario. "
            "Please provide a clearer name or machine code.")
    if len(mac_hits) > 1:
        names = ", ".join(sorted({m.name for m in mac_hits.values()}))
        raise WhatIfError(
            f"That matches more than one machine ({names}). Please use the full name or code.")
    mac = next(iter(mac_hits.values()))
    reason = "maintenance" if any(h in lowered for h in ("maintenance", "repair", "rest")) else "unavailable"
    return {"type": "MACHINE_UNAVAILABLE", "machine_id": mac.id,
            "entity_name": mac.name, "duration_hours": duration, "reason": reason}


# --------------------------------------------------------------------------
# Deterministic impact simulation (plain dicts only, never ORM writes)
# --------------------------------------------------------------------------

def _task_dict(t: Task) -> Dict[str, Any]:
    return {"id": str(t.id), "name": t.name,
            "order_id": str(t.order_id) if t.order_id else None,
            "current_progress": t.progress if t.progress is not None else 0.0,
            "status": t.status}


def _open_tasks_for_employee(db: Session, employee_id: UUID) -> List[Task]:
    tasks = db.query(Task).filter(Task.employee_id == employee_id).all()
    return [t for t in tasks if _norm(t.status) not in CLOSED_TASK_STATUSES]


def _covering_alternatives(db: Session, task: Task, exclude_id: UUID) -> List[Employee]:
    """Available employees who could take over one task (real data only).

    A task with a required skill needs a skill match via the existing
    matcher; a task without one accepts any ACTIVE + AVAILABLE employee.
    Ranked by lightest current load. Never invents suitability.
    """
    from backend.services.matcher import _skill_match, open_task_count, skills_of

    need = (task.required_skill or "").strip()
    scored = []
    for e in db.query(Employee).filter(Employee.id != exclude_id).all():
        if _norm(e.status) != "ACTIVE" or _norm(e.availability) != "AVAILABLE":
            continue
        if need and not _skill_match(skills_of(e), need):
            continue
        scored.append((open_task_count(db, e.id), e))
    scored.sort(key=lambda s: s[0])
    return [e for _, e in scored]


def simulate_employee_leave(db: Session, employee_id: UUID, duration_hours: float) -> Dict[str, Any]:
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if emp is None:
        raise WhatIfError("Employee not found in this factory.", status_code=404)
    affected = _open_tasks_for_employee(db, emp.id)
    order_ids = sorted({str(t.order_id) for t in affected if t.order_id})

    prod_count = 0
    if affected:
        tids = [t.id for t in affected]
        prod_count = db.query(ProductionRun).filter(
            ProductionRun.task_id.in_(tids),
            ProductionRun.status.notin_(list(FINISHED_RUN_STATUSES | {"CANCELLED"})),
        ).count()

    alternatives, uncovered = [], 0
    per_task_alt: Dict[str, Employee] = {}
    for t in affected:
        alts = _covering_alternatives(db, t, emp.id)
        if alts:
            per_task_alt[str(t.id)] = alts[0]
        else:
            uncovered += 1
    seen = set()
    for t in affected:
        alt = per_task_alt.get(str(t.id))
        if alt and alt.id not in seen:
            seen.add(alt.id)
            alternatives.append({
                "type": "employee", "id": str(alt.id), "name": alt.name,
                "reason": f"{alt.role or 'Staff'} is AVAILABLE with {len(db.query(Task).filter(Task.employee_id == alt.id).all())} open task(s); "
                          f"covers '{t.name}'" + (f" (skill: {t.required_skill})" if t.required_skill else ""),
            })

    delay = 0.0 if not affected else (0.0 if uncovered == 0 else float(duration_hours))
    if affected and uncovered == 0:
        recommendation = (
            f"Reassign the {len(affected)} affected task(s) to {alternatives[0]['name']} "
            f"during the absence. Expected order delay: 0 hours.")
    elif affected:
        first = affected[0]
        alt = per_task_alt.get(str(first.id))
        if alt:
            recommendation = (
                f"Reassign Task {first.name} to {alt.name} ({alt.role or 'staff'}). "
                f"{uncovered} task(s) have no cover; expected order delay: {delay:g} hours.")
        else:
            recommendation = (
                f"No suitable replacement is currently available for {first.name}. "
                f"The affected order(s) may be delayed by approximately {delay:g} hours.")
    else:
        recommendation = f"{emp.name} has no open tasks. No impact expected."
    return {
        "entity_name": emp.name, "entity_id": str(emp.id),
        "affected_tasks": [_task_dict(t) for t in affected],
        "affected_order_ids": order_ids,
        "affected_production_runs": prod_count,
        "estimated_delay_hours": delay,
        "estimated_units_at_risk": 0,
        "alternatives": alternatives,
        "recommendation": recommendation,
        "assumptions": [
            f"{emp.name} treated as UNAVAILABLE for {duration_hours:g} hours (simulation only).",
            "Delay assumes uncovered open tasks slip by the full absence window.",
        ],
    }


def simulate_machine_unavailable(db: Session, machine_id: UUID,
                                 duration_hours: float, reason: str) -> Dict[str, Any]:
    mac = db.query(Machine).filter(Machine.id == machine_id).first()
    if mac is None:
        raise WhatIfError("Machine not found in this factory.", status_code=404)
    runs = db.query(ProductionRun).filter(
        ProductionRun.machine_id == mac.id,
        ProductionRun.status.in_(list(ACTIVE_RUN_STATUSES)),
    ).all()
    task_ids = sorted({str(r.task_id) for r in runs if r.task_id})
    tasks = db.query(Task).filter(Task.id.in_([r.task_id for r in runs if r.task_id])).all() \
        if task_ids else []
    order_ids = sorted({str(x) for x in
                        ([r.order_id for r in runs if r.order_id] +
                         [t.order_id for t in tasks if t.order_id])})
    units = sum(max(0, int(r.quantity_target or 0) - int(r.quantity_completed or 0)) for r in runs)

    alternatives = []
    if mac.machine_type:
        for m in db.query(Machine).all():
            if m.id == mac.id or _norm(m.status) != "OPERATIONAL":
                continue
            if (m.machine_type or "").strip().lower() == (mac.machine_type or "").strip().lower():
                alternatives.append({
                    "type": "machine", "id": str(m.id), "name": m.name,
                    "reason": f"Same type ({m.machine_type}), OPERATIONAL, health {m.health_status or 'GOOD'}",
                })

    delay = 0.0 if not runs else (0.0 if alternatives else float(duration_hours))
    if runs and alternatives:
        recommendation = (
            f"Move the affected production to {alternatives[0]['name']} during the {reason} window. "
            f"{alternatives[0]['name']} is available and suitable. Expected order delay: 0 hours.")
    elif runs:
        recommendation = (
            f"No suitable replacement machine is currently available. "
            f"The affected order(s) may be delayed by approximately {delay:g} hours "
            f"({units} unit(s) at risk).")
    else:
        recommendation = f"{mac.name} has no active production runs. No impact expected."
    return {
        "entity_name": mac.name, "entity_id": str(mac.id),
        "affected_tasks": [_task_dict(t) for t in tasks],
        "affected_order_ids": order_ids,
        "affected_production_runs": len(runs),
        "estimated_delay_hours": delay,
        "estimated_units_at_risk": units,
        "alternatives": alternatives,
        "recommendation": recommendation,
        "assumptions": [
            f"{mac.name} treated as UNAVAILABLE for {duration_hours:g} hours ({reason}; simulation only).",
            "Delay assumes active runs stall for the full window without a replacement machine.",
        ],
    }
