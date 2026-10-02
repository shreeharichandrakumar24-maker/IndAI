"""Smart Split endpoint (mobile-app Phase 3). Prefix /ai, route /smart-split.

Interim contract: deterministic context + candidate pre-filter, LLM picks
within candidates, strict validation (unknown ids dropped/cleared), honest
rule-based fallback without a key. Task creation stays a separate,
explicit frontend action through POST /tasks.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.schemas.ai import SmartSplitBody, SplitProposal
from backend.services.llm import LLMUnavailable, complete_json
from backend.services.smart_split import candidates_for, rule_based_proposal, split_context

router = APIRouter()

SPLIT_SYSTEM_PROMPT = """You split a factory order into production tasks.
You receive the order, profile task templates, and per-template-slot candidate workers/machines (pre-filtered: available + skill match, healthy + type match + free).
Rules: output JSON ONLY {summary, proposed_tasks[{name, description, required_skill, priority (LOW/NORMAL/HIGH/URGENT), machine_id (exact UUID from that slot's candidates or null), employee_id (exact UUID from that slot's candidates or null), suggested_deadline (ISO or null), rationale (one line citing skill/load/health facts)}]}; one row per template slot, same order; never invent ids; null when no candidate fits; keep priorities sane vs the order priority. Output JSON ONLY."""


@router.post("/smart-split")
def smart_split(body: SmartSplitBody, db: Session = Depends(get_db)):
    try:
        ctx = split_context(db, body.order_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e).strip("'"))

    templates = ctx["task_templates"] or [{
        "name": f"Produce {ctx['order']['product'] or ctx['order']['order_number']}",
        "description": "", "required_skill": None, "machine_type": None,
    }]
    slots = []
    for t in templates[:10]:
        cands = candidates_for(db, t.get("required_skill") or "", t.get("machine_type") or "")
        slots.append({"template": t, "candidates": cands})

    try:
        result = complete_json(
            SPLIT_SYSTEM_PROMPT,
            {"order": ctx["order"],
             "slots": [{"template": s["template"], "candidates": s["candidates"]} for s in slots]},
            SplitProposal,
        )
        source = "ai"
        proposed = []
        for idx, p in enumerate(result.proposed_tasks[: len(slots)]):
            cands = slots[idx]["candidates"]
            emp_ids = {e["id"] for e in cands["employees"]}
            mac_ids = {m["id"] for m in cands["machines"]}
            emp = p.employee_id if p.employee_id in emp_ids else None
            mac = p.machine_id if p.machine_id in mac_ids else None
            dropped = []
            if p.employee_id and emp is None:
                dropped.append("employee not an eligible candidate")
            if p.machine_id and mac is None:
                dropped.append("machine not an eligible candidate")
            prio = (p.priority or "NORMAL").upper()
            if prio not in ("LOW", "NORMAL", "HIGH", "URGENT"):
                prio = "NORMAL"
            proposed.append({
                "name": p.name, "description": p.description or "",
                "required_skill": p.required_skill,
                "priority": prio, "machine_id": mac, "employee_id": emp,
                "suggested_deadline": p.suggested_deadline,
                "rationale": p.rationale + (" [dropped: " + "; ".join(dropped) + "]" if dropped else ""),
                "candidates": cands,
            })
        return {"source": source,
                "summary": result.summary,
                "order": ctx["order"],
                "proposed_tasks": proposed}
    except LLMUnavailable:
        pass

    fb = rule_based_proposal(db, ctx)
    return {"source": "rule-based", "summary": fb["summary"],
            "order": ctx["order"], "proposed_tasks": fb["proposed_tasks"]}
