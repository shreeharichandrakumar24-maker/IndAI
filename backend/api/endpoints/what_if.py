from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.schemas.what_if import WhatIfRequest, WhatIfResult
from backend.services import what_if as engine
from backend.services.llm import LLMUnavailable, complete_json

router = APIRouter()

WHAT_IF_NARRATIVE_PROMPT = """You narrate a factory what-if simulation for a non-technical manager.
You receive the parsed scenario, the deterministic impact computed from real
factory data, and the deterministic recommendation.
Rules: restate the impact in short plain sentences; clearly say the numbers
describe a SIMULATION, not real changes; never invent new numbers, names, or
stats beyond the input (you may restate them); if nothing is affected, say so
plainly. Output JSON ONLY: {narrative}."""


@router.post("/simulate", response_model=WhatIfResult)
def simulate_what_if(body: WhatIfRequest, db: Session = Depends(get_db)):
    """Natural-language what-if: ONE employee leave OR ONE machine downtime.

    Strictly read-only: the engine only SELECTs and builds plain dicts, and
    this endpoint commits nothing. Real data is identical before and after.
    """
    from pydantic import BaseModel

    text = (body.scenario or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="Describe a scenario first.")
    try:
        parsed = engine.parse_scenario(db, text)
        if parsed["type"] == "EMPLOYEE_LEAVE":
            sim = engine.simulate_employee_leave(db, parsed["employee_id"], parsed["duration_hours"])
        else:
            sim = engine.simulate_machine_unavailable(
                db, parsed["machine_id"], parsed["duration_hours"], parsed["reason"])
    except engine.WhatIfError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    n_tasks = len(sim["affected_tasks"])
    n_orders = len(sim["affected_order_ids"])
    summary = (
        f"{sim['entity_name']}'s simulated {parsed['duration_hours']:g}-hour "
        f"{'absence' if parsed['type'] == 'EMPLOYEE_LEAVE' else parsed['reason']} "
        f"may affect {n_tasks} task(s) across {n_orders} order(s)."
        if (n_tasks or n_orders) else
        f"{sim['entity_name']}'s simulated {parsed['duration_hours']:g}-hour "
        f"{'absence' if parsed['type'] == 'EMPLOYEE_LEAVE' else parsed['reason']}: "
        f"no open work affected."
    )
    scenario_info = {
        "type": parsed["type"],
        "entity_id": str(parsed.get("employee_id") or parsed.get("machine_id")),
        "entity_name": sim["entity_name"],
        "duration_hours": parsed["duration_hours"],
        "reason": parsed.get("reason"),
    }
    result = WhatIfResult(
        scenario=scenario_info,
        summary=summary,
        impact={"affected_tasks": n_tasks,
                "affected_orders": n_orders,
                "affected_production_runs": sim["affected_production_runs"],
                "estimated_delay_hours": sim["estimated_delay_hours"],
                "estimated_units_at_risk": sim["estimated_units_at_risk"]},
        affected_tasks=sim["affected_tasks"],
        affected_order_ids=sim["affected_order_ids"],
        alternatives=sim["alternatives"],
        recommendation=sim["recommendation"],
        assumptions=sim["assumptions"],
        simulation_only=True,
    )

    class _Narrative(BaseModel):
        narrative: str = ""

    try:
        nar = complete_json(WHAT_IF_NARRATIVE_PROMPT,
                            {"scenario": result.scenario.model_dump(),
                             "impact": result.impact.model_dump(),
                             "recommendation": result.recommendation},
                            _Narrative)
        result.narrative = nar.narrative
    except LLMUnavailable:
        result.narrative = None  # deterministic result stands alone
    return result
