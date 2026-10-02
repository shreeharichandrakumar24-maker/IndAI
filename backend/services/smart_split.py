"""Smart Split interim contract (mobile-app Phase 3).

Deterministic context first (order, profile templates/skills, machines with
health/incidents/load, employees with skills/availability/load), deterministic
candidate pre-filter per task, then the LLM picks within the candidates.
No key -> template-based rule split, labeled honestly.
"""
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from backend.models.models import Employee, Incident, Machine, Order, ProductionRun, Task
from backend.services.matcher import match_machine, match_worker, open_task_count, skills_of

OPEN_INCIDENT = ("OPEN", "IN_PROGRESS")


def split_context(db: Session, order_id: UUID) -> Dict[str, Any]:
    order = db.query(Order).filter(Order.id == order_id).first()
    if order is None:
        raise KeyError("Order not found")

    templates: List[Dict[str, Any]] = []
    skills: List[str] = []
    try:
        from backend.models.models import FactoryProfile
        prof = (
            db.query(FactoryProfile).filter(FactoryProfile.status == "APPROVED")
            .order_by(FactoryProfile.updated_at.desc()).first()
        )
        if prof is not None and isinstance(prof.profile, dict):
            templates = prof.profile.get("task_templates") or []
            skills = prof.profile.get("skills") or []
    except Exception:
        pass

    machines = db.query(Machine).all()
    open_incs = db.query(Incident).filter(Incident.status.in_(list(OPEN_INCIDENT))).all()
    bad_machines = {i.machine_id for i in open_incs if i.machine_id}
    active_runs = db.query(ProductionRun).filter(
        ProductionRun.status.in_(["IN_PROGRESS", "RUNNING"])).all()
    busy_machines = {r.machine_id for r in active_runs if r.machine_id}
    employees = db.query(Employee).all()

    return {
        "order": {
            "id": str(order.id), "order_number": order.order_number,
            "customer_name": order.customer_name, "product": order.product,
            "quantity": order.quantity, "priority": order.priority,
            "status": order.status,
            "deadline": order.deadline.isoformat() if order.deadline else None,
            "progress": order.progress,
        },
        "task_templates": templates,
        "profile_skills": skills,
        "machines": [
            {"id": str(m.id), "name": m.name, "machine_type": m.machine_type,
             "status": m.status, "health_status": m.health_status,
             "has_open_incident": m.id in bad_machines,
             "has_active_run": m.id in busy_machines}
            for m in machines
        ],
        "employees": [
            {"id": str(e.id), "name": e.name, "role": e.role,
             "skills": skills_of(e)[:12],
             "certifications": e.certifications, "shift": e.shift,
             "availability": e.availability, "status": e.status}
            for e in employees
        ],
    }


def candidates_for(db: Session, required_skill: str = "", machine_type: str = "") -> Dict[str, List[Dict[str, Any]]]:
    """Deterministic pre-filter: eligible + ranked employees/machines."""

    emps: List[Dict[str, Any]] = []
    try:
        for e in db.query(Employee).all():
            if (e.status or "ACTIVE").upper() != "ACTIVE":
                continue
            if (e.availability or "AVAILABLE").upper() != "AVAILABLE":
                continue
            sk = skills_of(e)
            if required_skill and not any(required_skill.strip().lower() in s or s in required_skill.strip().lower() for s in sk):
                continue
            emps.append({"id": str(e.id), "name": e.name,
                         "open_tasks": open_task_count(db, e.id), "shift": e.shift})
    except Exception:
        pass
    emps.sort(key=lambda x: (x["open_tasks"], x["name"] or ""))

    machs: List[Dict[str, Any]] = []
    try:
        bad = {i.machine_id for i in db.query(Incident)
               .filter(Incident.status.in_(list(OPEN_INCIDENT))).all() if i.machine_id}
        for m in db.query(Machine).all():
            if machine_type and (m.machine_type or "").strip().lower() != machine_type.strip().lower():
                continue
            if (m.status or "OPERATIONAL").upper() != "OPERATIONAL":
                continue
            if m.id in bad:
                continue
            machs.append({"id": str(m.id), "name": m.name,
                          "health_status": m.health_status or "GOOD"})
    except Exception:
        pass
    machs.sort(key=lambda x: (0 if (x["health_status"] or "").upper() == "GOOD" else 1, x["name"] or ""))
    return {"employees": emps[:10], "machines": machs[:10]}


def rule_based_proposal(db: Session, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Template fallback when the LLM is unavailable. Labeled as rule-based."""
    templates = ctx["task_templates"] or [{
        "name": f"Produce {ctx['order']['product'] or ctx['order']['order_number']}",
        "description": "Generic production task (no profile templates configured).",
        "required_skill": None, "machine_type": None,
    }]
    proposed = []
    for t in templates[:10]:
        cands = candidates_for(db, t.get("required_skill") or "", t.get("machine_type") or "")
        emp = cands["employees"][0] if cands["employees"] else None
        mac = cands["machines"][0] if cands["machines"] else None
        proposed.append({
            "name": t.get("name") or "Production step",
            "description": t.get("description") or "",
            "required_skill": t.get("required_skill"),
            "priority": ctx["order"]["priority"] or "NORMAL",
            "machine_id": mac["id"] if mac else None,
            "employee_id": emp["id"] if emp else None,
            "suggested_deadline": ctx["order"]["deadline"],
            "rationale": "Template step from the approved factory profile. " +
                         (f"Worker {emp['name']} (lowest load). " if emp else "No eligible worker found. ") +
                         (f"Machine {mac['name']} (healthy, free). " if mac else "No free healthy machine of type. ") +
                         "Rule-based: AI unavailable.",
            "candidates": cands,
        })
    return {"summary": f"Rule-based split of {ctx['order']['order_number']} into {len(proposed)} step(s) from profile templates (AI unavailable).",
            "proposed_tasks": proposed}
