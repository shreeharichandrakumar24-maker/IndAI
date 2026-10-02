"""Candidate snapshots + AI suggestion validation for Feature 6.

Snapshot builders are deterministic (same eligibility as matcher.py).
The LLM only ranks within the snapshot; invented ids are dropped and the
deterministic matcher is the labeled fallback when the LLM is unavailable.
"""
from typing import Any, Dict, List
from uuid import UUID

from sqlalchemy.orm import Session

from backend.models.models import Employee, Machine
from backend.services.matcher import open_task_count, skills_of


def candidate_workers(db: Session, limit: int = 15) -> List[Dict[str, Any]]:
    out = []
    try:
        employees = db.query(Employee).all()
    except Exception:
        return out
    for e in employees:
        if (e.status or "ACTIVE").upper() != "ACTIVE":
            continue
        if (e.availability or "AVAILABLE").upper() != "AVAILABLE":
            continue
        out.append({
            "id": str(e.id),
            "name": e.name or "",
            "skills": skills_of(e)[:12],
            "open_tasks": open_task_count(db, e.id),
            "shift": e.shift,
        })
        if len(out) >= limit:
            break
    return out


def candidate_machines(db: Session, limit: int = 10) -> List[Dict[str, Any]]:
    out = []
    try:
        machines = db.query(Machine).all()
    except Exception:
        return out
    for m in machines:
        if (m.status or "OPERATIONAL").upper() != "OPERATIONAL":
            continue
        out.append({
            "id": str(m.id),
            "name": m.name or "",
            "machine_type": m.machine_type,
            "health_status": m.health_status,
        })
        if len(out) >= limit:
            break
    return out


def validate_suggestions(raw_items: List[Dict[str, Any]], valid_assignment_ids: set,
                         valid_employee_ids: set, valid_machine_ids: set) -> List[Dict[str, Any]]:
    """Drop anything referencing ids outside the snapshot. Never throws."""
    kept = []
    for s in raw_items or []:
        try:
            if not isinstance(s, dict):
                continue
            if s.get("assignment_id") not in valid_assignment_ids:
                continue
            emp = s.get("employee_id")
            mac = s.get("machine_id")
            if emp is not None and emp not in valid_employee_ids:
                emp = None
            if mac is not None and mac not in valid_machine_ids:
                mac = None
            score = float(s.get("score", 0.5))
            score = max(0.0, min(1.0, score))
            reasons = [str(r) for r in (s.get("reasons") or [])][:5]
            if emp is None:
                kept.append({"assignment_id": s["assignment_id"], "employee_id": None,
                             "machine_id": mac, "score": 0.0,
                             "reasons": reasons or ["No suitable worker in snapshot."],
                             "status": "UNASSIGNABLE"})
            else:
                kept.append({"assignment_id": s["assignment_id"], "employee_id": emp,
                             "machine_id": mac, "score": score,
                             "reasons": reasons, "status": "SUGGESTED"})
        except Exception:
            continue
    return kept
