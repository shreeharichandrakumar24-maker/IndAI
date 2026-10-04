"""Worker self-service (Part 2). Prefix /worker. Token REQUIRED everywhere.

Every route is scoped to the caller: only rows whose employee_id is the
caller's are visible or mutable (anything else is 404, same shape as not
found). Reuses existing models/services; existing endpoints untouched.
"""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.endpoints.worker_auth import get_current_worker
from backend.db.database import get_db
from backend.models.models import Employee, Incident, Machine, MachineTelemetry, Order, ProductionRun, Task

router = APIRouter()

ALLOWED_AVAILABILITY = ("AVAILABLE", "BUSY", "UNAVAILABLE")
TASK_FLOW = {"PENDING": ("IN_PROGRESS",), "IN_PROGRESS": ("COMPLETED", "DONE")}


def _labels(db: Session, task: Task) -> dict:
    out = {"order_number": None, "machine_name": None}
    if task.order_id:
        o = db.query(Order).filter(Order.id == task.order_id).first()
        if o is not None:
            out["order_number"] = o.order_number
    if task.machine_id:
        m = db.query(Machine).filter(Machine.id == task.machine_id).first()
        if m is not None:
            out["machine_name"] = m.name
    return out


def _task_payload(db: Session, task: Task) -> dict:
    return {
        "id": str(task.id),
        "name": task.name,
        "description": task.description,
        "required_skill": task.required_skill,
        "priority": task.priority,
        "status": task.status,
        "employee_id": str(task.employee_id) if task.employee_id else None,
        "machine_id": str(task.machine_id) if task.machine_id else None,
        "order_id": str(task.order_id) if task.order_id else None,
        "start_time": task.start_time.isoformat() if task.start_time else None,
        "deadline": task.deadline.isoformat() if task.deadline else None,
        "progress": task.progress,
        **_labels(db, task),
    }


def _own_task(db: Session, employee_id, task_id: UUID) -> Task:
    task = db.query(Task).filter(Task.id == task_id).first()
    if task is None or task.employee_id != employee_id:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/me")
def worker_me(current=Depends(get_current_worker), db: Session = Depends(get_db)):
    employee, _cred = current
    mine = db.query(Task).filter(Task.employee_id == employee.id).all()
    open_t = [t for t in mine if (t.status or "").upper() in ("PENDING", "IN_PROGRESS")]
    done_t = [t for t in mine if (t.status or "").upper() in ("COMPLETED", "DONE", "CANCELLED")]
    upcoming = sorted([t.deadline for t in open_t if t.deadline])
    return {
        "id": str(employee.id),
        "name": employee.name,
        "role": employee.role,
        "shift": employee.shift,
        "status": employee.status,
        "availability": employee.availability,
        "skills": employee.skills,
        "certifications": employee.certifications,
        "stats": {
            "assigned": len(mine),
            "active": len(open_t),
            "done": len(done_t),
            "next_deadline": upcoming[0].isoformat() if upcoming else None,
        },
    }


@router.get("/tasks")
def worker_tasks(current=Depends(get_current_worker), db: Session = Depends(get_db)):
    employee, _cred = current
    tasks = db.query(Task).filter(Task.employee_id == employee.id).order_by(Task.created_at.desc()).all()
    return [_task_payload(db, t) for t in tasks]


@router.get("/tasks/{task_id}")
def worker_task(task_id: UUID, current=Depends(get_current_worker), db: Session = Depends(get_db)):
    employee, _cred = current
    task = _own_task(db, employee.id, task_id)
    payload = _task_payload(db, task)
    tel = None
    if task.machine_id:
        tel = (db.query(MachineTelemetry).filter(MachineTelemetry.machine_id == task.machine_id)
               .order_by(MachineTelemetry.timestamp.desc()).first())
    payload["latest_telemetry"] = None if tel is None else {
        "temperature": tel.temperature, "vibration": tel.vibration,
        "current": tel.current, "rpm": tel.rpm,
        "machine_status": tel.machine_status,
        "timestamp": tel.timestamp.isoformat() if tel.timestamp else None,
    }
    return payload


@router.put("/tasks/{task_id}/status")
def worker_task_status(task_id: UUID, body: dict, current=Depends(get_current_worker),
                       db: Session = Depends(get_db)):
    employee, _cred = current
    task = _own_task(db, employee.id, task_id)
    want = str((body or {}).get("status") or "").upper()
    allowed = TASK_FLOW.get((task.status or "PENDING").upper(), ())
    if want not in allowed:
        raise HTTPException(status_code=422, detail=f"Allowed from {task.status}: {list(allowed) or 'none'}.")
    from_status = (task.status or "PENDING").upper()
    task.status = want
    if want == "IN_PROGRESS" and task.start_time is None:
        task.start_time = datetime.now(timezone.utc)
    if want in ("COMPLETED", "DONE"):
        task.progress = 1.0
    db.commit()
    db.refresh(task)
    # Plan-tracking history (best-effort; never fails this request).
    from backend.services.activity import log_task_activity
    log_task_activity(db, task=task, employee=employee,
                      action="completed" if want in ("COMPLETED", "DONE") else "started",
                      from_status=from_status, to_status=want, progress=task.progress)
    return _task_payload(db, task)


@router.put("/tasks/{task_id}/progress")
def worker_task_progress(task_id: UUID, body: dict, current=Depends(get_current_worker),
                         db: Session = Depends(get_db)):
    employee, _cred = current
    task = _own_task(db, employee.id, task_id)
    try:
        pct = float((body or {}).get("progress", -1))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="progress must be a number 0..1.")
    if not 0.0 <= pct <= 1.0:
        raise HTTPException(status_code=422, detail="progress must be a number 0..1.")
    task.progress = pct
    db.commit()
    db.refresh(task)
    from backend.services.activity import log_task_activity
    log_task_activity(db, task=task, employee=employee, action="progress",
                      from_status=(task.status or "PENDING").upper(),
                      to_status=(task.status or "PENDING").upper(), progress=pct)
    return _task_payload(db, task)


@router.post("/tasks/{task_id}/output")
def worker_task_output(task_id: UUID, body: dict, current=Depends(get_current_worker),
                       db: Session = Depends(get_db)):
    employee, _cred = current
    task = _own_task(db, employee.id, task_id)
    try:
        qty = int((body or {}).get("quantity", -1))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="quantity must be an integer.")
    if qty < 0:
        raise HTTPException(status_code=422, detail="quantity must be an integer.")
    run = None
    if task.order_id:
        runs = db.query(ProductionRun).filter(ProductionRun.order_id == task.order_id).all()
        run = next((r for r in runs if r.task_id == task.id), None) or (runs[0] if runs else None)
    if run is None:
        raise HTTPException(status_code=404, detail="No production run for this task.")
    if qty > (run.quantity_target or 0) and (run.quantity_target or 0) > 0 \
            and not bool((body or {}).get("confirm")):
        raise HTTPException(status_code=422, detail=f"Over target ({run.quantity_target}). Resend with confirm=true.")
    run.quantity_completed = qty
    db.commit()
    db.refresh(run)
    from backend.services.activity import log_task_activity
    log_task_activity(db, task=task, employee=employee, action="output",
                      quantity_completed=qty, quantity_target=run.quantity_target)
    return {"id": str(run.id), "quantity_target": run.quantity_target,
            "quantity_completed": run.quantity_completed, "status": run.status}


@router.post("/incidents")
def worker_report_incident(body: dict, current=Depends(get_current_worker),
                           db: Session = Depends(get_db)):
    from backend.models.models import Incident
    employee, _cred = current
    task = None
    if (body or {}).get("task_id"):
        try:
            task = db.query(Task).filter(Task.id == UUID(str(body["task_id"]))).first()
        except (ValueError, AttributeError):
            task = None
        if task is None or task.employee_id != employee.id:
            raise HTTPException(status_code=404, detail="Task not found")
    sev = str((body or {}).get("severity") or "MEDIUM").upper()
    if sev not in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        raise HTTPException(status_code=422, detail="severity must be LOW, MEDIUM, HIGH or CRITICAL.")
    desc = str((body or {}).get("description") or "").strip()
    if not desc:
        raise HTTPException(status_code=422, detail="description is required.")
    inc = Incident(
        machine_id=task.machine_id if task else None,
        task_id=task.id if task else None,
        employee_id=employee.id,
        order_id=task.order_id if task else None,
        incident_type="WORKER_REPORT",
        severity=sev,
        description=f"[Worker report] {desc} (by {employee.name})"[:2000],
        status="OPEN",
    )
    db.add(inc)
    db.commit()
    db.refresh(inc)
    return {"id": str(inc.id), "incident_type": inc.incident_type, "severity": inc.severity,
            "status": inc.status, "machine_id": str(inc.machine_id) if inc.machine_id else None,
            "task_id": str(inc.task_id) if inc.task_id else None,
            "order_id": str(inc.order_id) if inc.order_id else None}


@router.put("/availability")
def worker_availability(body: dict, current=Depends(get_current_worker),
                        db: Session = Depends(get_db)):
    employee, _cred = current
    value = str((body or {}).get("availability") or "").upper()
    if value not in ALLOWED_AVAILABILITY:
        raise HTTPException(status_code=422, detail=f"availability must be one of {list(ALLOWED_AVAILABILITY)}.")
    employee.availability = value
    db.commit()
    db.refresh(employee)
    return {"id": str(employee.id), "availability": employee.availability}


@router.get("/alerts")
def worker_alerts(current=Depends(get_current_worker), db: Session = Depends(get_db)):
    """OPEN incidents touching the caller's work: own tasks, own machines,
    own orders. Newest first."""
    from backend.models.models import Incident
    employee, _cred = current
    mine = db.query(Task).filter(Task.employee_id == employee.id).all()
    tids = {t.id for t in mine}
    mids = {t.machine_id for t in mine if t.machine_id}
    oids = {t.order_id for t in mine if t.order_id}
    rows = db.query(Incident).filter(Incident.status == "OPEN").order_by(Incident.created_at.desc()).all()
    out = []
    for i in rows:
        if (i.task_id in tids) or (i.machine_id in mids) or (i.order_id in oids):
            out.append({
                "id": str(i.id), "incident_type": i.incident_type, "severity": i.severity,
                "status": i.status, "description": (i.description or "")[:300],
                "machine_id": str(i.machine_id) if i.machine_id else None,
                "task_id": str(i.task_id) if i.task_id else None,
                "order_id": str(i.order_id) if i.order_id else None,
                "created_at": i.created_at.isoformat() if i.created_at else None,
            })
    return out
