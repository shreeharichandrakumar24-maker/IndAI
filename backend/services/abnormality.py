"""Deterministic abnormal-telemetry detection for the
IoT abnormality -> incident -> maintenance workflow.

Application-level demo thresholds only. No threshold columns or tables exist
(or are needed): the constants below are the single place to change them.
The simulator's own thresholds are untouched.

Rules (breach = abnormal):
- temperature > TEMP_ABNORMAL
- vibration > VIBRATION_ABNORMAL
- current > CURRENT_ABNORMAL
- rpm < RPM_ABNORMAL_MIN
- machine_status in ABNORMAL_STATUSES

A reading that is None (sensor absent) is skipped: a machine is judged only
on its available readings.

Severity (deterministic):
- CRITICAL if machine_status is MAINTENANCE or STOPPED
- HIGH if 2 or more numeric conditions are breached
- MEDIUM otherwise
"""
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from backend.models.models import Incident, Machine, MachineTelemetry

# ---- Demo thresholds (single source of truth) ----
# Defaults = the original constants. When a factory_profile row with
# status APPROVED exists, per-machine_type thresholds from the profile
# override these (Phase D). Missing table / no approved profile -> defaults.
TEMP_ABNORMAL = 85.0
VIBRATION_ABNORMAL = 5.0
CURRENT_ABNORMAL = 10.0
RPM_ABNORMAL_MIN = 1300.0
ABNORMAL_STATUSES = frozenset({"MAINTENANCE", "STOPPED"})

# Active statuses (discovered from frontend conventions + tone helpers):
# - ProductionRun: PLANNED default; IN_PROGRESS/RUNNING = active; COMPLETED/DONE/CANCELLED = closed.
# - Task: PENDING default; IN_PROGRESS = active; COMPLETED/DONE/CANCELLED = closed.
ACTIVE_PRODUCTION_STATUSES = ("IN_PROGRESS", "RUNNING")
ACTIVE_TASK_STATUSES = ("IN_PROGRESS",)

INCIDENT_TYPE_ABNORMAL_TELEMETRY = "MACHINE_ABNORMAL_TELEMETRY"
INCIDENT_STATUS_OPEN = "OPEN"


def default_thresholds() -> Dict[str, float]:
    """Fallback deterministic thresholds (original constants)."""
    return {
        "temp_max": TEMP_ABNORMAL,
        "vibration_max": VIBRATION_ABNORMAL,
        "current_max": CURRENT_ABNORMAL,
        "rpm_min": RPM_ABNORMAL_MIN,
    }


def resolve_thresholds(machine_type: Optional[str], db: Optional[Session] = None,
                       factory_id: Optional[UUID] = None) -> Dict[str, float]:
    """Per-machine_type thresholds from the approved factory profile.

    Deterministic. Falls back to defaults when no approved profile exists
    or the table is missing (fresh installs before migration 001).

    Multi-company: when ``factory_id`` is given (the machine's owning
    factory) that factory's approved thresholds are used. ``factory_id``
    None keeps the legacy behavior (newest approved profile).
    """
    base = default_thresholds()
    if db is None:
        return base
    try:
        from backend.models.models import FactoryProfile
        q = db.query(FactoryProfile).filter(FactoryProfile.status == "APPROVED")
        if factory_id is not None:
            row = q.filter(FactoryProfile.id == factory_id).first()
        else:
            row = q.order_by(FactoryProfile.updated_at.desc()).first()
        if row is None or not isinstance(row.profile, dict):
            return base
        sets = (row.profile or {}).get("thresholds") or {}
        cand = sets.get(machine_type) or sets.get("_default")
        if not isinstance(cand, dict):
            return base
        out = dict(base)
        for k in ("temp_max", "vibration_max", "current_max", "rpm_min"):
            try:
                if cand.get(k) is not None:
                    out[k] = float(cand[k])
            except (TypeError, ValueError):
                continue
        return out
    except Exception:
        return base


def _breach(field: str, observed: Any, expected: str) -> Dict[str, Any]:
    return {"field": field, "observed": observed, "expected": expected}


def evaluate_telemetry(
    row: Optional[MachineTelemetry], thresholds: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """Pure detection: judge one telemetry row against the thresholds.

    Returns {"abnormal": bool, "breaches": [...], "severity": str|None}.
    severity is None when the row is normal or absent.
    `thresholds` overrides the defaults (per machine_type from the approved
    profile); when None the built-in defaults apply. Return shape unchanged.
    """
    if row is None:
        return {"abnormal": False, "breaches": [], "severity": None}

    th = thresholds or default_thresholds()
    temp_max = th.get("temp_max", TEMP_ABNORMAL)
    vib_max = th.get("vibration_max", VIBRATION_ABNORMAL)
    curr_max = th.get("current_max", CURRENT_ABNORMAL)
    rpm_min = th.get("rpm_min", RPM_ABNORMAL_MIN)

    breaches: List[Dict[str, Any]] = []
    numeric_breaches = 0

    if row.temperature is not None and row.temperature > temp_max:
        breaches.append(_breach("temperature", row.temperature, f"<= {temp_max}"))
        numeric_breaches += 1
    if row.vibration is not None and row.vibration > vib_max:
        breaches.append(_breach("vibration", row.vibration, f"<= {vib_max}"))
        numeric_breaches += 1
    if row.current is not None and row.current > curr_max:
        breaches.append(_breach("current", row.current, f"<= {curr_max}"))
        numeric_breaches += 1
    if row.rpm is not None and row.rpm < rpm_min:
        breaches.append(_breach("rpm", row.rpm, f">= {rpm_min}"))
        numeric_breaches += 1

    status = (row.machine_status or "").upper()
    status_breach = status in ABNORMAL_STATUSES
    if status_breach:
        breaches.append(_breach("machine_status", row.machine_status, "not MAINTENANCE/STOPPED"))

    abnormal = len(breaches) > 0
    severity = None
    if abnormal:
        if status_breach:
            severity = "CRITICAL"
        elif numeric_breaches >= 2:
            severity = "HIGH"
        else:
            severity = "MEDIUM"
    return {"abnormal": abnormal, "breaches": breaches, "severity": severity}


def is_normal(row: Optional[MachineTelemetry], thresholds: Optional[Dict[str, float]] = None) -> bool:
    """Inverse of evaluate_telemetry: True only when available readings are
    all within bounds. None (no telemetry) is NOT normal."""
    if row is None:
        return False
    return not evaluate_telemetry(row, thresholds)["abnormal"]


def latest_telemetry(db: Session, machine_id: UUID) -> Optional[MachineTelemetry]:
    return (
        db.query(MachineTelemetry)
        .filter(MachineTelemetry.machine_id == machine_id)
        .order_by(MachineTelemetry.timestamp.desc())
        .first()
    )


def open_incident_for_machine(db: Session, machine_id: UUID) -> Optional[Incident]:
    return (
        db.query(Incident)
        .filter(Incident.machine_id == machine_id, Incident.status == INCIDENT_STATUS_OPEN)
        .order_by(Incident.created_at.desc())
        .first()
    )


def _describe_breaches(breaches: List[Dict[str, Any]]) -> str:
    parts = []
    for b in breaches:
        parts.append(f"{b['field']}={b['observed']} (expected {b['expected']})")
    return "; ".join(parts)


def _enrich_incident_links(db: Session, machine_id: UUID) -> Dict[str, Optional[UUID]]:
    """Find unambiguous active links for a new incident (existing columns only).

    Deterministic. Prefers the single active production run on the machine
    (IN_PROGRESS/RUNNING), else the single active task (IN_PROGRESS).
    Returns {task_id, order_id, employee_id} with None where ambiguous/absent.
    """
    from backend.models.models import ProductionRun, Task

    links: Dict[str, Optional[UUID]] = {"task_id": None, "order_id": None, "employee_id": None}
    try:
        runs = (
            db.query(ProductionRun)
            .filter(
                ProductionRun.machine_id == machine_id,
                ProductionRun.status.in_(list(ACTIVE_PRODUCTION_STATUSES)),
            )
            .all()
        )
    except Exception:
        runs = []
    if len(runs) == 1:
        run = runs[0]
        links["order_id"] = run.order_id
        links["task_id"] = run.task_id
    try:
        db_tasks = (
            db.query(Task)
            .filter(
                Task.machine_id == machine_id,
                Task.status.in_(list(ACTIVE_TASK_STATUSES)),
            )
            .all()
        )
    except Exception:
        db_tasks = []
    task = None
    if links["task_id"] is not None:
        try:
            from backend.models.models import Task as TaskModel
            task = db.query(TaskModel).filter(TaskModel.id == links["task_id"]).first()
        except Exception:
            task = None
    elif len(db_tasks) == 1:
        task = db_tasks[0]
        links["task_id"] = task.id
    if task is not None:
        if links["order_id"] is None:
            links["order_id"] = task.order_id
        links["employee_id"] = task.employee_id
    elif links["task_id"] is None and links["order_id"] is None and len(db_tasks) == 1:
        links["task_id"] = db_tasks[0].id
        links["order_id"] = db_tasks[0].order_id
        links["employee_id"] = db_tasks[0].employee_id
    return links


def detect_and_create_incident(db: Session, machine_id: UUID) -> Dict[str, Any]:
    """Inspect latest telemetry for one machine; create an OPEN incident if
    abnormal and none already exists. Never duplicates OPEN incidents.
    Returns a display-ready result dict (machine UUIDs as strings)."""
    machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if machine is None:
        return {"machine_id": str(machine_id), "found": False}

    row = latest_telemetry(db, machine_id)
    if row is None:
        return {
            "machine_id": str(machine_id),
            "found": True,
            "has_telemetry": False,
            "abnormal": False,
            "breaches": [],
            "severity": None,
            "incident_created": False,
            "incident_id": None,
        }

    result = evaluate_telemetry(row, resolve_thresholds(machine.machine_type, db, machine.factory_id))
    outcome: Dict[str, Any] = {
        "machine_id": str(machine_id),
        "found": True,
        "has_telemetry": True,
        "abnormal": result["abnormal"],
        "breaches": result["breaches"],
        "severity": result["severity"],
        "latest_timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "incident_created": False,
        "incident_id": None,
    }
    if not result["abnormal"]:
        return outcome

    existing = open_incident_for_machine(db, machine_id)
    if existing is not None:
        outcome["incident_id"] = str(existing.id)
        outcome["already_existed"] = True
        return outcome

    links = _enrich_incident_links(db, machine_id)
    incident = Incident(
        machine_id=machine_id,
        task_id=links["task_id"],
        order_id=links["order_id"],
        employee_id=links["employee_id"],
        incident_type=INCIDENT_TYPE_ABNORMAL_TELEMETRY,
        severity=result["severity"],
        description=(
            f"Abnormal telemetry on {machine.name}: {_describe_breaches(result['breaches'])}."
        ),
        status=INCIDENT_STATUS_OPEN,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    outcome["incident_created"] = True
    outcome["incident_id"] = str(incident.id)
    # Phase 2 bell (deterministic, never breaks ingestion).
    try:
        from backend.services.notify import notify_incident, notify_order_risk
        notify_incident(db, machine.name, result["severity"], incident.id)
        if links["order_id"] is not None:
            from datetime import datetime, timezone
            from backend.models.models import Order, ProductionRun
            from backend.services.context import deterministic_order_risk
            order = db.query(Order).filter(Order.id == links["order_id"]).first()
            if order is not None:
                runs = db.query(ProductionRun).filter(ProductionRun.order_id == order.id).all()
                remaining = sum(max(0, (r.quantity_target or 0) - (r.quantity_completed or 0)) for r in runs)
                if remaining <= 0:
                    remaining = max(0, int((order.quantity or 0) * (1 - (order.progress or 0))))
                hours = None
                if order.deadline:
                    dl = order.deadline if order.deadline.tzinfo else order.deadline.replace(tzinfo=timezone.utc)
                    hours = (dl - datetime.now(timezone.utc)).total_seconds() / 3600
                risk = deterministic_order_risk(remaining, hours, machine_down=True)
                notify_order_risk(db, order.order_number, risk)
    except Exception:
        pass
    return outcome


def health_of_machine(db: Session, machine_id: UUID) -> Dict[str, Any]:
    """Recovery check: NORMAL only when latest available readings are all
    within bounds. Never resolves incidents — the admin workflow does that."""
    machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if machine is None:
        return {"machine_id": str(machine_id), "found": False}
    row = latest_telemetry(db, machine_id)
    if row is None:
        return {
            "machine_id": str(machine_id),
            "found": True,
            "has_telemetry": False,
            "normal": None,
            "latest_timestamp": None,
            "breaches": [],
        }
    result = evaluate_telemetry(row, resolve_thresholds(machine.machine_type, db, machine.factory_id))
    return {
        "machine_id": str(machine_id),
        "found": True,
        "has_telemetry": True,
        "normal": not result["abnormal"],
        "latest_timestamp": row.timestamp.isoformat() if row.timestamp else None,
        "breaches": result["breaches"],
    }
