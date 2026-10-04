"""AI analysis + recommendation decisions (Phase E). Prefix /ai."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.models.models import AIRecommendation, FactoryMemory, Incident, Maintenance
from backend.schemas.ai import AssistantReply, ChatBody, DecisionBody, IncidentAnalysis, RecommendationResponse, RootCauseAnalysis, RootCauseScope, SimulateBody, SimulationResult
from backend.services.assistant_context import build_assistant_context
from backend.services.context import build_incident_context
from backend.services.cross_context import build_cross_context
from backend.services.llm import LLMUnavailable, complete_json

router = APIRouter()

PROPOSAL_ACTIONS = ("SCHEDULE_MAINTENANCE", "REASSIGN_TASK", "DELAY_TASK")


class ProposalBody(BaseModel):
    action_type: str
    params: dict = {}
    reason: str = ""


@router.post("/proposals", response_model=RecommendationResponse)
def create_proposal(body: ProposalBody, db: Session = Depends(get_db)):
    """Thin validated creator over the Phase-4 flow (Part B). Nothing executes
    here; approval stays on PATCH /recommendations/{id}/decision."""
    from backend.models.models import Employee as EmpModel, Machine as MacModel, Task as TaskModel

    action = (body.action_type or "").upper()
    if action not in PROPOSAL_ACTIONS:
        raise HTTPException(status_code=422, detail=f"Use one of {list(PROPOSAL_ACTIONS)}.")
    params = dict(body.params or {})

    def need_uuid(value, label, model):
        try:
            row = db.query(model).filter(model.id == UUID(str(value))).first()
        except (ValueError, AttributeError):
            row = None
        if row is None:
            raise HTTPException(status_code=422, detail=f"Unknown {label}.")
        return str(row.id)

    clean: dict = {}
    if action == "SCHEDULE_MAINTENANCE":
        if not params.get("machine_id"):
            raise HTTPException(status_code=422, detail="machine_id is required.")
        clean["machine_id"] = need_uuid(params["machine_id"], "machine", MacModel)
        clean["issue"] = str(params.get("issue") or "Scheduled check")[:200]
    elif action == "REASSIGN_TASK":
        if not params.get("task_id"):
            raise HTTPException(status_code=422, detail="task_id is required.")
        clean["task_id"] = need_uuid(params["task_id"], "task", TaskModel)
        if params.get("employee_id"):
            emp = db.query(EmpModel).filter(EmpModel.id == UUID(str(params["employee_id"]))).first() \
                if _is_uuid(params["employee_id"]) else None
            if emp is None:
                raise HTTPException(status_code=422, detail="Unknown employee.")
            if (emp.status or "ACTIVE").upper() != "ACTIVE" or (emp.availability or "AVAILABLE").upper() != "AVAILABLE":
                if not params.get("override") is True:
                    raise HTTPException(status_code=422, detail=f"{emp.name} is not available; pass override=true to assign anyway.")
            clean["employee_id"] = str(emp.id)
            clean["override"] = bool(params.get("override"))
        if params.get("machine_id"):
            clean["machine_id"] = need_uuid(params["machine_id"], "machine", MacModel)
        if "employee_id" not in clean and "machine_id" not in clean:
            raise HTTPException(status_code=422, detail="Nothing to change.")
    elif action == "DELAY_TASK":
        if not params.get("task_id"):
            raise HTTPException(status_code=422, detail="task_id is required.")
        clean["task_id"] = need_uuid(params["task_id"], "task", TaskModel)
        try:
            from datetime import datetime
            datetime.fromisoformat(str(params.get("new_deadline")).replace("Z", "+00:00"))
        except (ValueError, AttributeError, TypeError):
            raise HTTPException(status_code=422, detail="Bad new_deadline (ISO datetime required).")
        clean["new_deadline"] = str(params["new_deadline"])

    title = {"SCHEDULE_MAINTENANCE": "Schedule maintenance",
             "REASSIGN_TASK": "Reassign task",
             "DELAY_TASK": "Delay task"}[action]
    row = AIRecommendation(
        recommendation_type=action, entity_type="PROPOSAL", entity_id=UUID(str(clean.get("task_id") or clean.get("machine_id"))),
        recommendation=title, reason=(body.reason or "")[:2000] or None,
        confidence=None, status="PENDING",
    )
    row.params = clean
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/proposals", response_model=list[RecommendationResponse])
def list_proposals(status: str | None = None, db: Session = Depends(get_db)):
    """Pending proposals (entity PROPOSAL). Same rows the decision endpoint acts on."""
    q = db.query(AIRecommendation).filter(AIRecommendation.entity_type == "PROPOSAL")
    if status:
        q = q.filter(AIRecommendation.status == status.upper())
    return q.order_by(AIRecommendation.created_at.desc()).limit(200).all()


def _is_uuid(value) -> bool:
    try:
        UUID(str(value))
        return True
    except (ValueError, AttributeError):
        return False

ANALYSIS_SYSTEM_PROMPT = """You are a factory reliability analyst. Given a JSON snapshot of an incident (machine, telemetry, breaches vs thresholds, production, orders, maintenance history), explain the incident.
Rules:
- Use ONLY facts present in the snapshot. Cite the sensor values and order numbers you used.
- If data is missing, say "insufficient data" instead of guessing.
- root_cause: one summary sentence + contributing factors + confidence 0-1.
- order_risk: one entry per affected order_id in the snapshot (use those exact UUID strings), risk LOW/MEDIUM/HIGH with a one-line reason and estimated_delay_hours or null.
- recommendations: 1-4 actions, each action_type one of SCHEDULE_MAINTENANCE, REASSIGN_TASK, DELAY_TASK, MONITOR, ESCALATE, with a short title and detail.
- Output JSON ONLY."""


@router.post("/analyze-incident/{incident_id}")
def analyze_incident(incident_id: UUID, db: Session = Depends(get_db)):
    try:
        snapshot = build_incident_context(db, incident_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Incident not found")
    valid_order_ids = {o["id"] for o in snapshot.get("orders", [])}
    try:
        analysis = complete_json(ANALYSIS_SYSTEM_PROMPT, {"snapshot": snapshot}, IncidentAnalysis)
    except LLMUnavailable as e:
        # Graceful degradation: deterministic facts only, labeled AI unavailable.
        raise HTTPException(status_code=503, detail=f"AI unavailable: {e}. Deterministic risk is available; retry when the LLM key is configured.")

    # Drop any order ids the model invented (must exist in the snapshot).
    kept_risk = [r for r in analysis.order_risk if r.order_id in valid_order_ids]
    analysis.order_risk = kept_risk

    # Persist each recommendation (status PENDING) for the admin decision step.
    saved: list[AIRecommendation] = []
    for rec in analysis.recommendations:
        row = AIRecommendation(
            recommendation_type=rec.action_type,
            entity_type="INCIDENT",
            entity_id=incident_id,
            recommendation=f"{rec.title} — {rec.detail}".strip(" —"),
            reason=rec.detail,
            confidence=analysis.root_cause.confidence,
            status="PENDING",
        )
        db.add(row)
        saved.append(row)
    db.commit()
    for row in saved:
        db.refresh(row)
    # Phase 2 bell: managers approve every recommendation.
    try:
        from backend.services.notify import notify_approvals
        notify_approvals(db, len(saved))
    except Exception:
        pass

    return {
        "incident_id": str(incident_id),
        "source": "ai",
        "root_cause": analysis.root_cause.model_dump(),
        "order_risk_ai": [r.model_dump() for r in analysis.order_risk],
        "deterministic_risk": snapshot["deterministic_risk"],
        "recommendations": [RecommendationResponse.model_validate(r).model_dump(mode="json") for r in saved],
        "snapshot_facts": {
            "breaches": snapshot["breaches"],
            "latest_reading": snapshot["latest_reading"],
            "thresholds": snapshot["thresholds"],
        },
    }


CHAT_SYSTEM_PROMPT = """You are IndAI, a plain-language factory assistant for a non-technical manager.
You receive a JSON snapshot of the factory (machines, open incidents, active orders, open tasks, pending recommendations) plus the conversation.
Rules:
- Answer in short plain sentences. No jargon (never say telemetry, deterministic, abnormality).
- Use ONLY facts present in the snapshot. Name the machines/orders/tasks you used.
- If the snapshot lacks the data, say "I don't have that data" instead of guessing.
- You may propose at most 2 actions, ONLY these kinds:
  SCHEDULE_MAINTENANCE {machine_id (exact UUID from snapshot), issue (short text)} for a machine with an open incident;
  UPDATE_TASK_STATUS {task_id (exact UUID from snapshot), status one of PENDING, IN_PROGRESS, DONE} when the user asks to start/complete a task.
- Every machine_id/task_id must be copied exactly from the snapshot. Anything else will be dropped.
- Output JSON ONLY: {answer, used_facts[], proposed_actions[]}."""


@router.post("/chat")
def chat(body: ChatBody, db: Session = Depends(get_db)):
    message = (body.message or "").strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message is empty.")
    if len(message) > 2000:
        raise HTTPException(status_code=422, detail="Message too long (max 2000 chars).")
    snapshot = build_assistant_context(db)
    valid_machines = {m["id"] for m in snapshot["machines"]}
    valid_tasks = {t["id"] for t in snapshot["open_tasks"]}
    try:
        reply = complete_json(
            CHAT_SYSTEM_PROMPT,
            {"snapshot": snapshot, "history": body.history[-10:], "message": message},
            AssistantReply,
        )
    except LLMUnavailable as e:
        raise HTTPException(status_code=503, detail=f"AI unavailable: {e}. Try again when the LLM key is configured.")

    # Drop invented ids and illegal statuses; keep only executable proposals.
    kept = []
    for a in reply.proposed_actions:
        if a.action_type == "SCHEDULE_MAINTENANCE":
            if a.machine_id in valid_machines and (a.issue or "").strip():
                kept.append(a)
        elif a.action_type == "UPDATE_TASK_STATUS":
            if a.task_id in valid_tasks and (a.status or "").upper() in ("PENDING", "IN_PROGRESS", "DONE"):
                a.status = a.status.upper()
                kept.append(a)
    reply.proposed_actions = kept[:2]
    return {
        "source": "ai",
        "answer": reply.answer,
        "used_facts": reply.used_facts,
        "proposed_actions": [a.model_dump() for a in reply.proposed_actions],
    }


ROOT_CAUSE_SYSTEM_PROMPT = """You are a cross-system factory diagnostician. Given a JSON snapshot joining telemetry summaries, tasks, orders, production runs, incidents, maintenance history, and past memory for one scope (a machine and/or an order), find the root cause.
Rules:
- Correlate ACROSS systems: link sensor breaches to stalled tasks, missed maintenance, late orders. Say which systems each claim comes from.
- Use ONLY facts present in the snapshot. Quote the values/ids you used.
- If evidence is thin, say "insufficient data" and name what is missing.
- Output JSON ONLY: {primary_cause (one or two sentences), evidence[] ({system one of telemetry|tasks|orders|maintenance|memory|incidents, fact one line}), confidence 0-1, related_ids {machines[], orders[], tasks[], incidents[]} using EXACT UUID strings from the snapshot}.
- Anything not in the snapshot will be dropped."""


@router.post("/root-cause")
def root_cause(body: RootCauseScope, db: Session = Depends(get_db)):
    if not body.machine_id and not body.order_id:
        raise HTTPException(status_code=422, detail="Provide machine_id or order_id.")
    try:
        snapshot = build_cross_context(db, body.machine_id, body.order_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    valid = {
        "machines": {m["id"] for m in snapshot["machines"]},
        "orders": {o["id"] for o in snapshot["orders"]},
        "tasks": {t["id"] for t in snapshot["tasks"]},
        "incidents": {i["id"] for i in snapshot["incidents"]},
    }
    allowed_systems = {"telemetry", "tasks", "orders", "maintenance", "memory", "incidents"}
    try:
        result = complete_json(ROOT_CAUSE_SYSTEM_PROMPT, {"snapshot": snapshot}, RootCauseAnalysis)
    except LLMUnavailable as e:
        raise HTTPException(status_code=503, detail=f"AI unavailable: {e}. Snapshot facts are available; retry when the LLM key is configured.")
    result.evidence = [e for e in result.evidence if e.system in allowed_systems]
    for key in ("machines", "orders", "tasks", "incidents"):
        ids = getattr(result.related_ids, key)
        setattr(result.related_ids, key, [i for i in ids if i in valid[key]])
    return {
        "source": "ai",
        "scope": snapshot["scope"],
        "primary_cause": result.primary_cause,
        "evidence": [e.model_dump() for e in result.evidence],
        "confidence": result.confidence,
        "related_ids": result.related_ids.model_dump(),
        "snapshot_facts": {
            "current_breaches": snapshot["current_breaches"],
            "incidents": len(snapshot["incidents"]),
            "open_tasks": len(snapshot["tasks"]),
        },
    }


SIMULATE_SYSTEM_PROMPT = """You narrate a factory what-if simulation for a non-technical manager.
You receive the scenario, the deterministic projection (old vs new risk per order, deltas, feasibility verdicts, assumptions).
Rules: explain in short plain sentences what changes and what does not; name the orders/numbers used; never invent new numbers beyond the projection (you may restate them); if nothing changes, say so plainly. Output JSON ONLY: {narrative}."""


class _Narrative(BaseModel):
    narrative: str = ""


@router.post("/simulate", response_model=SimulationResult)
def simulate(body: SimulateBody, db: Session = Depends(get_db)):
    """Display-only what-if projection. Writes nothing; applying for real
    happens through the normal endpoints (approval gate intact)."""
    from backend.services import simulator as sim

    try:
        if body.scenario_type == "DELAY_ORDER":
            if not body.order_id or body.days is None:
                raise HTTPException(status_code=422, detail="DELAY_ORDER needs order_id and days.")
            proj = sim.simulate_delay_order(db, body.order_id, body.days)
        elif body.scenario_type == "RESOLVE_INCIDENT":
            if not body.incident_id:
                raise HTTPException(status_code=422, detail="RESOLVE_INCIDENT needs incident_id.")
            proj = sim.simulate_resolve_incident(db, body.incident_id)
        elif body.scenario_type == "REASSIGN_TASK":
            if not body.task_id or (not body.employee_id and not body.machine_id):
                raise HTTPException(status_code=422, detail="REASSIGN_TASK needs task_id and employee_id and/or machine_id.")
            proj = sim.simulate_reassign_task(db, body.task_id, body.employee_id, body.machine_id)
        else:
            raise HTTPException(status_code=422, detail="Unknown scenario.")
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e).strip("'"))

    result = SimulationResult.model_validate(proj)
    try:
        nar = complete_json(SIMULATE_SYSTEM_PROMPT,
                            {"scenario": body.scenario_type, "projection": result.model_dump()},
                            _Narrative)
        result.narrative = nar.narrative
    except LLMUnavailable:
        result.narrative = None  # deterministic numbers stand alone; labeled by absence
    return result


@router.get("/recommendations")
def list_recommendations(entity_id: UUID | None = None, status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(AIRecommendation).order_by(AIRecommendation.created_at.desc())
    if entity_id:
        q = q.filter(AIRecommendation.entity_id == entity_id)
    if status:
        q = q.filter(AIRecommendation.status == status)
    return [RecommendationResponse.model_validate(r).model_dump(mode="json") for r in q.limit(200).all()]


@router.patch("/recommendations/{rec_id}/decision")
def decide_recommendation(rec_id: UUID, body: DecisionBody, db: Session = Depends(get_db)):
    rec = db.query(AIRecommendation).filter(AIRecommendation.id == rec_id).first()
    if rec is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    if rec.status != "PENDING":
        raise HTTPException(status_code=409, detail=f"Already decided ({rec.status}). Decisions are idempotent: one decision only.")

    rec.status = body.decision

    # Assistant/Jarvis proposals carry structured params (migration 005).
    # Degrade clearly when the column is missing instead of half-applying.
    try:
        params = dict(getattr(rec, "params", None) or {})
        params_ok = True
    except Exception:
        params, params_ok = {}, False
    if rec.entity_type == "ASSISTANT" and not params_ok:
        db.rollback()
        raise HTTPException(status_code=500, detail="params column missing — run backend/db/migrations/005_ai_recommendation_params.sql first.")

    # Gather links from the incident snapshot for the memory row.
    machine_id = order_id = task_id = None
    root_summary = ""
    try:
        if rec.entity_type == "INCIDENT":
            inc = db.query(Incident).filter(Incident.id == rec.entity_id).first()
            if inc is not None:
                machine_id, order_id, task_id = inc.machine_id, inc.order_id, inc.task_id
        elif rec.entity_type in ("ASSISTANT", "PROPOSAL"):
            # Derive links from the validated params (+ task row for order).
            from backend.models.models import Task as TaskModel
            if params.get("machine_id"):
                try:
                    machine_id = UUID(str(params["machine_id"]))
                except (ValueError, AttributeError):
                    machine_id = None
            if params.get("task_id"):
                try:
                    task_id = UUID(str(params["task_id"]))
                    trow = db.query(TaskModel).filter(TaskModel.id == task_id).first()
                    if trow is not None:
                        order_id = trow.order_id
                        if machine_id is None:
                            machine_id = trow.machine_id
                except (ValueError, AttributeError):
                    task_id = None
    except Exception:
        pass

    mem = FactoryMemory(
        title=f"{body.decision}: {rec.recommendation_type} on {rec.entity_type} {str(rec.entity_id)[:8]}",
        event_type="ADMIN_DECISION",
        description=(body.note or rec.recommendation or "")[:2000],
        machine_id=machine_id,
        order_id=order_id,
        task_id=task_id,
        resolution_action=rec.recommendation,
        metadata_={
            "recommendation_id": str(rec.id),
            "action_type": rec.recommendation_type,
            "decision": body.decision,
            "root_cause_summary": root_summary,
            "admin_note": body.note,
            "entity_type": rec.entity_type,
            "entity_id": str(rec.entity_id),
        },
    )
    db.add(mem)

    maintenance_id = None
    task_id_created = None
    # Approved actions execute via the real schemas. Validation first, then
    # one transaction: any execution failure rolls everything back so the
    # decision stays PENDING and nothing is half-applied.
    if body.decision == "APPROVED" and rec.recommendation_type in (
        "SCHEDULE_MAINTENANCE", "REASSIGN_TASK", "DELAY_TASK", "DRAFT_ASSIGNMENT",
    ):
        from backend.models.models import Employee as EmployeeModel, Machine as MachineModel, Task as TaskModel2
        try:
            if rec.recommendation_type == "SCHEDULE_MAINTENANCE":
                mid = machine_id
                if mid is None and params.get("machine_id"):
                    mid = UUID(str(params["machine_id"]))
                if mid is None or db.query(MachineModel).filter(MachineModel.id == mid).first() is None:
                    raise ValueError("no valid machine for maintenance")
                issue = str(params.get("issue") or rec.recommendation or "Assistant-scheduled check")[:200]
                m = Maintenance(machine_id=mid, issue=f"AI recommendation {str(rec.id)[:8]}: {issue}",
                                description=rec.reason, status="PENDING")
                db.add(m)
                db.flush()
                maintenance_id = str(m.id)
            elif rec.recommendation_type == "REASSIGN_TASK":
                if task_id is None:
                    raise ValueError("no valid task to reassign")
                trow = db.query(TaskModel2).filter(TaskModel2.id == task_id).first()
                if trow is None:
                    raise ValueError("task no longer exists")
                changed = False
                if params.get("employee_id"):
                    emp = db.query(EmployeeModel).filter(EmployeeModel.id == UUID(str(params["employee_id"]))).first()
                    if emp is None:
                        raise ValueError("employee no longer exists")
                    trow.employee_id = emp.id
                    changed = True
                if params.get("machine_id"):
                    mac = db.query(MachineModel).filter(MachineModel.id == UUID(str(params["machine_id"]))).first()
                    if mac is None:
                        raise ValueError("machine no longer exists")
                    trow.machine_id = mac.id
                    changed = True
                if not changed:
                    raise ValueError("nothing to change")
            elif rec.recommendation_type == "DELAY_TASK":
                if task_id is None:
                    raise ValueError("no valid task to delay")
                trow = db.query(TaskModel2).filter(TaskModel2.id == task_id).first()
                if trow is None:
                    raise ValueError("task no longer exists")
                from datetime import datetime
                new_dl = datetime.fromisoformat(str(params.get("new_deadline")).replace("Z", "+00:00"))
                trow.deadline = new_dl
            elif rec.recommendation_type == "DRAFT_ASSIGNMENT":
                name = str(params.get("task_name") or "").strip()
                if not name:
                    raise ValueError("no task name to create")
                prio = str(params.get("priority") or "NORMAL").upper()
                if prio not in ("LOW", "NORMAL", "HIGH", "URGENT"):
                    prio = "NORMAL"
                new_task = TaskModel2(
                    name=name[:255],
                    description=str(params.get("description") or "")[:2000] or None,
                    required_skill=str(params.get("required_skill") or "")[:255] or None,
                    priority=prio,
                    status="PENDING",
                    progress=0.0,
                )
                if params.get("employee_id"):
                    emp = db.query(EmployeeModel).filter(EmployeeModel.id == UUID(str(params["employee_id"]))).first()
                    if emp is None:
                        raise ValueError("employee no longer exists")
                    new_task.employee_id = emp.id
                if params.get("machine_id"):
                    mac = db.query(MachineModel).filter(MachineModel.id == UUID(str(params["machine_id"]))).first()
                    if mac is None:
                        raise ValueError("machine no longer exists")
                    new_task.machine_id = mac.id
                if params.get("order_id"):
                    from backend.models.models import Order as OrderModel
                    ord_row = db.query(OrderModel).filter(OrderModel.id == UUID(str(params["order_id"]))).first()
                    if ord_row is None:
                        raise ValueError("order no longer exists")
                    new_task.order_id = ord_row.id
                    order_id = ord_row.id
                db.add(new_task)
                db.flush()
                task_id_created = str(new_task.id)
                task_id = new_task.id
                mem.task_id = new_task.id
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Action failed, nothing applied: {str(e)[:200]}")

    db.commit()
    db.refresh(rec)
    db.refresh(mem)
    return {
        "recommendation": RecommendationResponse.model_validate(rec).model_dump(mode="json"),
        "memory_id": str(mem.id),
        "maintenance_id": maintenance_id,
        "task_id": task_id_created,
    }


class _AutonomyBody(BaseModel):
    autonomy: str


@router.get("/autonomy")
def get_ai_autonomy(db: Session = Depends(get_db)):
    """Autonomy mode (FAST|ASK) for direct voice/text commands. Absent = FAST."""
    from backend.services import commands as _svc
    return {"autonomy": _svc.get_autonomy(db)}


@router.put("/autonomy")
def put_ai_autonomy(body: _AutonomyBody, db: Session = Depends(get_db)):
    from backend.services import commands as _svc
    return {"autonomy": _svc.set_autonomy(db, body.autonomy)}
