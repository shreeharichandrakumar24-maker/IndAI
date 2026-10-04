"""Assistant read tools (mobile-app Phase 4). Deterministic, compact, row-capped.

Every tool returns a small dict with a one-line `summary` (shown in the UI
"Data used" trace) plus the rows the model may cite. Tool results are
UNTRUSTED data for the model, never instructions.
"""
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.models.models import (
    Employee,
    FactoryMemory,
    Incident,
    Machine,
    MachineTelemetry,
    Maintenance,
    Order,
    ProductionRun,
    Task,
)

CAP = 20
OPEN_INCIDENT = ("OPEN", "IN_PROGRESS")
CLOSED_ORDER = ("COMPLETED", "DONE", "CANCELLED")


def _resolve_machine(db: Session, ref: str) -> Optional[Machine]:
    ref = (ref or "").strip()
    if not ref:
        return None
    try:
        return db.query(Machine).filter(Machine.id == UUID(ref)).first()
    except (ValueError, AttributeError):
        pass
    # Spoken forms ("M 001", "M zero zero one") via the shared normalizer.
    from backend.services.resolve import normalize_machine_code
    spoken = normalize_machine_code(ref)
    code = spoken or ref.upper()
    for m in db.query(Machine).all():
        import re
        mm = re.match(r"^(M-\d{3})", (m.name or "").strip())
        if (mm and mm.group(1) == code) or (m.name or "").strip().lower() == ref.lower():
            return m
    return None


def _resolve_order(db: Session, ref: str) -> Optional[Order]:
    ref = (ref or "").strip()
    if not ref:
        return None
    try:
        return db.query(Order).filter(Order.id == UUID(ref)).first()
    except (ValueError, AttributeError):
        pass
    return db.query(Order).filter(Order.order_number == ref).first()


def _resolve_employee(db: Session, ref: str):
    ref = (ref or "").strip()
    if not ref:
        return None
    try:
        return db.query(Employee).filter(Employee.id == UUID(ref)).first()
    except (ValueError, AttributeError):
        pass
    # Employee codes ("EMP-001", "emp 001", "employee one") via the shared
    # normalizer — checked before the name fallback, additive only.
    from backend.models.models import WorkerCredential
    from backend.services.resolve import normalize_employee_code
    code = normalize_employee_code(ref)
    if code:
        cred = db.query(WorkerCredential).filter(
            WorkerCredential.employee_code == code).first()
        if cred is not None:
            hit = db.query(Employee).filter(Employee.id == cred.employee_id).first()
            if hit is not None:
                return hit
    return db.query(Employee).filter(Employee.name.ilike(f"%{ref}%")).first()


def factory_overview(db: Session) -> Dict[str, Any]:
    from backend.services.risk import compute_order_risks
    orders = db.query(Order).count()
    runs = db.query(ProductionRun).count()
    tasks = db.query(Task).count()
    machines = db.query(Machine).count()
    open_incs = db.query(Incident).filter(Incident.status.in_(list(OPEN_INCIDENT))).count()
    staff = db.query(Employee).all()
    risks = compute_order_risks(db)
    high = [r for r in risks if r["risk_level"] == "HIGH"][:5]
    return {
        "summary": f"{orders} orders, {runs} runs, {tasks} tasks, {machines} machines, {len(staff)} employees, {open_incs} open incidents; {len(high)} HIGH-risk orders.",
        "counts": {"orders": orders, "runs": runs, "tasks": tasks,
                   "machines": machines, "employees": len(staff), "open_incidents": open_incs},
        "employees": [{"name": e.name, "role": e.role,
                       "availability": e.availability or "AVAILABLE"} for e in staff[:20]],
        "high_risk_orders": [{"order_number": r["order_number"], "reason": r["reason"]} for r in high],
    }


def list_machines(db: Session) -> Dict[str, Any]:
    from backend.services.abnormality import evaluate_telemetry, resolve_thresholds
    rows = []
    for m in db.query(Machine).all():
        tel = (db.query(MachineTelemetry).filter(MachineTelemetry.machine_id == m.id)
               .order_by(MachineTelemetry.timestamp.desc()).first())
        open_n = db.query(Incident).filter(
            Incident.machine_id == m.id, Incident.status.in_(list(OPEN_INCIDENT))).count()
        state = "ok"
        if open_n:
            state = "alert"
        elif tel and evaluate_telemetry(tel, resolve_thresholds(m.machine_type, db))["abnormal"]:
            state = "abnormal"
        rows.append({"id": str(m.id), "name": m.name, "machine_type": m.machine_type,
                     "status": m.status, "health_status": m.health_status, "state": state,
                     "open_incidents": open_n,
                     "latest": {"temperature": tel.temperature, "vibration": tel.vibration,
                                "current": tel.current, "rpm": tel.rpm,
                                "machine_status": tel.machine_status} if tel else None})
        if len(rows) >= CAP:
            break
    return {"summary": f"{len(rows)} machines listed; states ok/alert/abnormal.",
            "machines": rows}


def get_machine(db: Session, machine_ref: str) -> Dict[str, Any]:
    m = _resolve_machine(db, machine_ref)
    if m is None:
        return {"summary": f"No machine matches '{machine_ref}'.", "machine": None}
    tel = (db.query(MachineTelemetry).filter(MachineTelemetry.machine_id == m.id)
           .order_by(MachineTelemetry.timestamp.desc()).limit(5).all())
    open_incs = db.query(Incident).filter(
        Incident.machine_id == m.id, Incident.status.in_(list(OPEN_INCIDENT))).all()
    tasks = db.query(Task).filter(Task.machine_id == m.id).limit(10).all()
    return {
        "summary": f"{m.name}: {len(open_incs)} open incident(s), {len(tasks)} task(s), {len(tel)} recent reading(s).",
        "machine": {"id": str(m.id), "name": m.name, "machine_type": m.machine_type,
                    "status": m.status, "health_status": m.health_status},
        "latest_readings": [{"temperature": t.temperature, "vibration": t.vibration,
                             "current": t.current, "rpm": t.rpm,
                             "machine_status": t.machine_status} for t in tel],
        "open_incidents": [{"id": str(i.id), "severity": i.severity,
                            "description": (i.description or "")[:200]} for i in open_incs],
        "tasks": [{"id": str(t.id), "name": t.name, "status": t.status} for t in tasks],
    }


def list_open_incidents(db: Session) -> Dict[str, Any]:
    rows = (db.query(Incident).filter(Incident.status.in_(list(OPEN_INCIDENT)))
            .order_by(Incident.created_at.desc()).limit(CAP).all())
    mach = {m.id: m.name for m in db.query(Machine).all()}
    return {
        "summary": f"{len(rows)} open incident(s).",
        "incidents": [{"id": str(i.id), "machine": mach.get(i.machine_id, "?"),
                       "severity": i.severity, "status": i.status,
                       "description": (i.description or "")[:200]} for i in rows],
    }


def get_incident_context(db: Session, incident_id: str) -> Dict[str, Any]:
    try:
        iid = UUID(str(incident_id))
    except (ValueError, AttributeError):
        return {"summary": f"Bad incident id '{incident_id}'.", "context": None}
    from backend.services.context import build_incident_context
    try:
        ctx = build_incident_context(db, iid)
    except KeyError:
        return {"summary": "Incident not found.", "context": None}
    return {"summary": f"Incident {ctx['incident']['severity']} on {ctx['machine']['name'] if ctx['machine'] else '?'}; "
                       f"{len(ctx['breaches'])} breach(es), {len(ctx['orders'])} linked order(s).",
            "context": ctx}


def get_order_status(db: Session, order_ref: str) -> Dict[str, Any]:
    o = _resolve_order(db, order_ref)
    if o is None:
        return {"summary": f"No order matches '{order_ref}'.", "order": None}
    runs = db.query(ProductionRun).filter(ProductionRun.order_id == o.id).all()
    tasks = db.query(Task).filter(Task.order_id == o.id).all()
    mach_ids = {r.machine_id for r in runs if r.machine_id} | {t.machine_id for t in tasks if t.machine_id}
    mach = {str(m.id): m.name for m in db.query(Machine).filter(Machine.id.in_(list(mach_ids))).all()} if mach_ids else {}
    emp_ids = {t.employee_id for t in tasks if t.employee_id}
    emp = {str(e.id): e.name for e in db.query(Employee).filter(Employee.id.in_(list(emp_ids))).all()} if emp_ids else {}
    from backend.services.risk import compute_order_risks
    risk = next((r for r in compute_order_risks(db) if r["order_id"] == str(o.id)), None)
    return {
        "summary": f"Order {o.order_number}: {o.status}, {len(runs)} run(s), {len(tasks)} task(s); risk {risk['risk_level'] if risk else 'n/a'}.",
        "order": {"id": str(o.id), "order_number": o.order_number, "product": o.product,
                  "quantity": o.quantity, "status": o.status, "priority": o.priority,
                  "progress": o.progress,
                  "deadline": o.deadline.isoformat() if o.deadline else None},
        "runs": [{"id": str(r.id), "status": r.status, "target": r.quantity_target,
                  "done": r.quantity_completed, "machine": mach.get(str(r.machine_id), "?")} for r in runs],
        "tasks": [{"id": str(t.id), "name": t.name, "status": t.status,
                   "employee": emp.get(str(t.employee_id), "?")} for t in tasks],
        "risk": risk,
    }


def list_tasks(db: Session, status: str = "", machine_id: str = "", order_id: str = "") -> Dict[str, Any]:
    q = db.query(Task)
    if status:
        q = q.filter(Task.status == status.upper())
    if machine_id:
        try:
            q = q.filter(Task.machine_id == UUID(machine_id))
        except (ValueError, AttributeError):
            return {"summary": "Bad machine_id.", "tasks": []}
    if order_id:
        try:
            q = q.filter(Task.order_id == UUID(order_id))
        except (ValueError, AttributeError):
            return {"summary": "Bad order_id.", "tasks": []}
    rows = q.limit(CAP).all()
    return {"summary": f"{len(rows)} task(s) match.",
            "tasks": [{"id": str(t.id), "name": t.name, "status": t.status,
                       "priority": t.priority, "required_skill": t.required_skill} for t in rows]}


def get_employee_workload(db: Session, employee_ref: str) -> Dict[str, Any]:
    # Empty ref = roster request, not a miss: list everyone with load.
    if not (employee_ref or "").strip():
        staff = db.query(Employee).all()
        roster = []
        for e in staff[:20]:
            open_t = db.query(Task).filter(
                Task.employee_id == e.id, Task.status.in_(["PENDING", "IN_PROGRESS"])).count()
            roster.append({"name": e.name, "role": e.role,
                           "availability": e.availability or "AVAILABLE",
                           "open_tasks": open_t})
        return {"summary": f"{len(staff)} employee(s) on record.",
                "roster": roster, "employee": None}
    e = _resolve_employee(db, employee_ref)
    if e is None:
        return {"summary": f"No employee matches '{employee_ref}'.", "employee": None}
    open_t = db.query(Task).filter(
        Task.employee_id == e.id, Task.status.in_(["PENDING", "IN_PROGRESS"])).all()
    return {
        "summary": f"{e.name}: {len(open_t)} open task(s), {e.availability or 'AVAILABLE'}.",
        "employee": {"id": str(e.id), "name": e.name, "role": e.role,
                     "shift": e.shift, "availability": e.availability, "status": e.status},
        "open_tasks": [{"id": str(t.id), "name": t.name, "status": t.status} for t in open_t[:CAP]],
    }


def search_factory_memory(db: Session, query: str = "", machine: str = "", order: str = "") -> Dict[str, Any]:
    q = db.query(FactoryMemory).order_by(FactoryMemory.created_at.desc())
    needle = (query or "").strip()
    if needle:
        like = f"%{needle}%"
        q = q.filter(or_(FactoryMemory.title.ilike(like),
                         FactoryMemory.description.ilike(like),
                         FactoryMemory.resolution_action.ilike(like)))
    if machine:
        m = _resolve_machine(db, machine)
        q = q.filter(FactoryMemory.machine_id == (m.id if m else None))
    if order:
        o = _resolve_order(db, order)
        q = q.filter(FactoryMemory.order_id == (o.id if o else None))
    rows = q.limit(CAP).all()
    return {"summary": f"{len(rows)} memor{'y' if len(rows) == 1 else 'ies'} match.",
            "entries": [{"id": str(r.id), "title": r.title, "event_type": r.event_type,
                         "description": (r.description or "")[:300],
                         "resolution_action": (r.resolution_action or "")[:300]} for r in rows]}


def draft_assignment(db: Session, task_name: str = "", skill: str = "",
                     worker: str = "", machine: str = "") -> Dict[str, Any]:
    """Resolve a spoken assignment request to real ids (or explain the miss).

    Matches worker by name (or by skill when no name fits), machine by code
    or type. Returns exact UUIDs for the proposal plus human reasons.
    Unknown names/skills come back empty so the model says insufficient data.
    """
    name = (task_name or "").strip() or "Requested job"
    emp = _resolve_employee(db, worker) if (worker or "").strip() else None
    emp_by_skill = None
    if emp is None and (skill or "").strip():
        from backend.services.matcher import match_worker
        emp_by_skill, _ = match_worker(db, skill)
    emp = emp or emp_by_skill
    mac = None
    if (machine or "").strip():
        mac = _resolve_machine(db, machine)
        if mac is None:
            from backend.services.matcher import match_machine
            mac, _ = match_machine(db, machine)
    reasons = []
    if emp is not None:
        reasons.append(f"Worker {emp.name} ({emp.role or 'no role'}).")
    else:
        reasons.append("No available worker matches.")
    if mac is not None:
        reasons.append(f"Machine {mac.name} ({mac.machine_type or 'no type'}).")
    elif (machine or "").strip():
        reasons.append("No matching machine found.")
    return {
        "summary": f"Draft '{name}': " + ("ready to propose." if emp is not None else "missing worker, cannot propose."),
        "task_name": name,
        "required_skill": (skill or "").strip() or None,
        "employee_id": str(emp.id) if emp else None,
        "employee_name": emp.name if emp else None,
        "machine_id": str(mac.id) if mac else None,
        "machine_name": mac.name if mac else None,
        "reasons": reasons,
    }


def execute_command(db: Session, action: str = "", text: str = "", employee: str = "",
                    machine: str = "", order: str = "", task_ref: str = "",
                    status: str = "", priority: str = "", deadline: str = "",
                    product: str = "", quantity: str = "", customer: str = "",
                    autopilot: str = "") -> Dict[str, Any]:
    """Execute a direct admin command NOW through the same service the voice
    agent uses (create/assign task, create order, change/reassign/mark task,
    schedule maintenance). Returns a one-sentence summary plus command_id so
    the UI can offer Undo. ASK autonomy becomes a proposal server-side."""
    from backend.services import commands as svc
    from fastapi import HTTPException
    a = (action or "").strip().lower()
    auto = str(autopilot).strip().lower() in ("1", "true", "yes", "y")

    def _int(v):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return 0

    try:
        if a in ("task", "assign_task", "create_task", "draft_assignment"):
            out = svc.run_create_task(
                db, text=(text or task_ref or "task"),
                employee_ref=employee or None, machine_ref=machine or None,
                order_ref=order or None, priority=priority or None,
                deadline_text=deadline or None, autopilot=auto,
                source="text-assistant")
        elif a in ("order", "create_order"):
            out = svc.run_create_order(
                db, product=product or text or "General", quantity=_int(quantity),
                customer=customer or None, autopilot=auto, source="text-assistant")
        elif a in ("change", "change_task", "reassign", "assign"):
            out = svc.run_change(
                db, task_ref=task_ref or None, employee_ref=employee or None,
                machine_ref=machine or None, deadline_text=deadline or None,
                priority=priority or None, status=status or None,
                autopilot=auto, source="text-assistant")
        elif a in ("maintenance", "schedule_maintenance"):
            out = svc.run_maintenance(
                db, machine_ref=machine or None, issue=text or None,
                autopilot=auto, source="text-assistant")
        else:
            return {"summary": f"Unknown command action '{action}'.",
                    "error": "bad action"}
    except HTTPException as e:
        d = e.detail
        if isinstance(d, dict):
            return {"summary": d.get("question") or "I need one more detail.",
                    "needs_question": d}
        return {"summary": str(d)}
    except Exception as e:  # never crash the assistant loop
        return {"summary": f"Command failed: {str(e)[:150]}"}
    out = dict(out)
    out["summary"] = out.get("summary") or "Done."
    return out


TOOLS = {
    "factory_overview": (factory_overview, []),
    "list_machines": (list_machines, []),
    "get_machine": (get_machine, ["machine_ref"]),
    "list_open_incidents": (list_open_incidents, []),
    "get_incident_context": (get_incident_context, ["incident_id"]),
    "get_order_status": (get_order_status, ["order_ref"]),
    "list_tasks": (list_tasks, ["status", "machine_id", "order_id"]),
    "get_employee_workload": (get_employee_workload, ["employee_ref"]),
    "search_factory_memory": (search_factory_memory, ["query", "machine", "order"]),
    "draft_assignment": (draft_assignment, ["task_name", "skill", "worker", "machine"]),
    "execute_command": (execute_command, [
        "action", "text", "employee", "machine", "order", "task_ref",
        "status", "priority", "deadline", "product", "quantity",
        "customer", "autopilot"]),
}


def run_tool(db: Session, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Run one read tool. Unknown tools / bad args are rejected, never crash."""
    entry = TOOLS.get(tool)
    if entry is None:
        return {"error": f"Unknown tool '{tool}'. Available: {sorted(TOOLS)}."}
    fn, params = entry
    try:
        kwargs = {p: args.get(p, "") for p in params} if params else {}
        out = fn(db, **kwargs)
        out["tool"] = tool
        return out
    except Exception as e:
        return {"tool": tool, "error": f"Tool failed: {str(e)[:200]}"}
