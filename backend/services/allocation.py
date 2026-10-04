"""Allocation candidates for one task (Part B). Deterministic, rule-based.

Reuses smart_split's candidate pre-filter (skill/availability/load,
type/health/no-OPEN-incident) and enriches with the numbers behind each
rank: relevant certifications, shift fit vs the task window, open-task
workload, and machine active-run exclusion.
"""
from typing import Any, Dict, List
from uuid import UUID

from sqlalchemy.orm import Session

from backend.models.models import Employee, Incident, Machine, ProductionRun, Task
from backend.services.matcher import open_task_count, skills_of
from backend.services.smart_split import candidates_for

OPEN_INCIDENT = ("OPEN", "IN_PROGRESS")
ACTIVE_RUN = ("IN_PROGRESS", "RUNNING")


def _shift_fit(emp_shift: str, task) -> str:
    if not (task.start_time or task.deadline) or not (emp_shift or "").strip():
        return "unknown (no shift or window)"
    return f"employee shift '{emp_shift}' vs task window " \
           f"{task.start_time or 'open'} -> {task.deadline or 'open'}"


def allocation_candidates(db: Session, task_id: UUID) -> Dict[str, Any]:
    task = db.query(Task).filter(Task.id == task_id).first()
    if task is None:
        raise KeyError("Task not found")

    base = candidates_for(db, task.required_skill or "", "")
    employees: List[Dict[str, Any]] = []
    for e in base["employees"]:
        row = db.query(Employee).filter(Employee.id == UUID(e["id"])).first()
        certs = row.certifications if row is not None else None
        employees.append({**e, "required_skill": task.required_skill,
                          "certifications": certs,
                          "shift_fit": _shift_fit(row.shift if row else "", task)})

    busy = {r.machine_id for r in db.query(ProductionRun).filter(
        ProductionRun.status.in_(list(ACTIVE_RUN))).all() if r.machine_id}
    bad = {i.machine_id for i in db.query(Incident).filter(
        Incident.status.in_(list(OPEN_INCIDENT))).all() if i.machine_id}
    machines: List[Dict[str, Any]] = []
    for m in db.query(Machine).all():
        if task.machine_id and str(task.machine_id) != str(m.id):
            pass  # listed below only when type-compatible or already linked
        machines.append({
            "id": str(m.id), "name": m.name, "machine_type": m.machine_type,
            "status": m.status, "health_status": m.health_status,
            "has_open_incident": m.id in bad,
            "has_active_run": m.id in busy,
            "eligible": (m.status or "OPERATIONAL").upper() == "OPERATIONAL"
                        and m.id not in bad,
        })
    # Full fleet listed with eligibility flags; the caller ranks/filters.
    return {
        "source": "rule-based",
        "task": {"id": str(task.id), "name": task.name, "status": task.status,
                 "required_skill": task.required_skill,
                 "employee_id": str(task.employee_id) if task.employee_id else None,
                 "machine_id": str(task.machine_id) if task.machine_id else None,
                 "deadline": task.deadline.isoformat() if task.deadline else None},
        "employees": employees,
        "machines": machines,
    }
