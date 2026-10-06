from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from backend.db.database import get_db

from backend.models.models import Order
from backend.schemas.order import OrderCreate, OrderUpdate, OrderResponse

router = APIRouter()

# Order statuses actually used across the app (Orders page active list,
# tone helpers, closed-order conventions). Blocks garbage strings while
# never breaking existing flows.
ORDER_STATUSES = {"PENDING", "PLANNED", "APPROVED", "IN_PROGRESS", "IN REVIEW", "REVIEW",
                  "COMPLETED", "DONE", "CANCELLED", "DELAYED", "AT_RISK", "BLOCKED"}


def _check_status(status):
    s = (status or "PENDING").strip().upper()
    if s not in ORDER_STATUSES:
        raise HTTPException(status_code=422, detail=f"Unknown order status '{status}'. Use one of {sorted(ORDER_STATUSES)}.")
    return s

RISK_SYSTEM_PROMPT = """You estimate delivery delays for factory orders.
You receive deterministic risk rows (remaining units, hours to deadline, machine-down flag, current level).
Rules: use ONLY these numbers; output JSON ONLY {estimates: [{order_id (exact UUID from input), estimated_delay_hours (number or null when on track), reason (one plain sentence)}]}; HIGH risk with a down machine and <72h deadline implies major delay; LOW risk implies null delay. Never invent orders."""


@router.get("/at-risk")
def orders_at_risk(ai: bool = False, db: Session = Depends(get_db)):
    """Live predictive risk per active order. Deterministic always; AI delay
    estimates only when ?ai=true AND the LLM key exists (else 503-safe
    fallback: estimates stay null, source stays deterministic)."""
    from backend.schemas.ai import DelayEstimates
    from backend.services.llm import LLMUnavailable, complete_json
    from backend.services.risk import compute_order_risks

    rows = compute_order_risks(db)
    source = "deterministic"
    if ai:
        try:
            result = complete_json(
                RISK_SYSTEM_PROMPT,
                {"orders": [{k: r[k] for k in ("order_id", "order_number", "risk_level", "reason", "numbers")} for r in rows]},
                DelayEstimates,
            )
            valid = {r["order_id"] for r in rows}
            by_id = {r["order_id"]: r for r in rows}
            for est in result.estimates:
                if est.order_id in valid:
                    by_id[est.order_id]["estimated_delay_hours"] = est.estimated_delay_hours
                    by_id[est.order_id]["ai_reason"] = est.reason
            source = "ai"
        except LLMUnavailable:
            pass
    return {"source": source, "count": len(rows), "orders": rows}


@router.post("/at-risk/notify")
def notify_at_risk(order_id: UUID, db: Session = Depends(get_db)):
    """Explicit manager/operator action: bell HIGH-risk status for one order."""
    from backend.models.models import AppUser, Notification
    from backend.services.risk import compute_order_risks

    rows = compute_order_risks(db)
    hit = next((r for r in rows if r["order_id"] == str(order_id)), None)
    if hit is None:
        raise HTTPException(status_code=404, detail="No active order with that id.")
    if hit["risk_level"] != "HIGH":
        return {"notified": False, "reason": f"Order is {hit['risk_level']}, not HIGH. No bell raised."}
    managers = db.query(AppUser).filter(AppUser.active == True, AppUser.role == "MANAGER").all()  # noqa: E712
    for u in managers:
        db.add(Notification(user_id=u.id, title=f"Order {hit['order_number']} is at high risk",
                            body=hit["reason"], link="orders", kind="ORDER_AT_RISK"))
    db.commit()
    return {"notified": True, "managers_notified": len(managers), "order_number": hit["order_number"]}

@router.post("", response_model=OrderResponse)
def create_order(order: OrderCreate, db: Session = Depends(get_db)):
    data = order.model_dump()
    data["status"] = _check_status(data.get("status"))
    db_order = Order(**data)
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return db_order

@router.get("", response_model=List[OrderResponse])
def get_orders(status: Optional[str] = None, priority: Optional[str] = None, order_by_deadline: bool = False, db: Session = Depends(get_db)):
    query = db.query(Order)
    if status:
        query = query.filter(Order.status == status.strip().upper())
    if priority:
        query = query.filter(Order.priority == priority)
    if order_by_deadline:
        query = query.order_by(Order.deadline)
    return query.all()

@router.get("/{order_id}", response_model=OrderResponse)
def get_order(order_id: UUID, db: Session = Depends(get_db)):
    db_order = db.query(Order).filter(Order.id == order_id).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")
    return db_order

@router.put("/{order_id}", response_model=OrderResponse)
def update_order(order_id: UUID, order: OrderUpdate, db: Session = Depends(get_db)):
    db_order = db.query(Order).filter(Order.id == order_id).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")
    update_data = order.model_dump(exclude_unset=True)
    if "status" in update_data:
        update_data["status"] = _check_status(update_data["status"])
    for key, value in update_data.items():
        setattr(db_order, key, value)
    db.commit()
    db.refresh(db_order)
    return db_order

@router.delete("/{order_id}")
def delete_order(order_id: UUID, db: Session = Depends(get_db)):
    db_order = db.query(Order).filter(Order.id == order_id).first()
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")
    db.delete(db_order)
    db.commit()
    return {"message": "Order deleted"}
