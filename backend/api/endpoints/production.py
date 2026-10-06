from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from backend.db.database import get_db

from backend.models.models import ProductionRun
from backend.schemas.production import ProductionRunCreate, ProductionRunUpdate, ProductionRunResponse
from backend.services.completion import sync_order_completion, sync_task_completion

router = APIRouter()

# Canonical statuses covering every value the app has ever used
# (PLANNED default, IN_PROGRESS/RUNNING active, COMPLETED/DONE closed,
# CANCELLED). Blocks garbage strings while never breaking existing flows.
RUN_STATUSES = {"PLANNED", "IN_PROGRESS", "RUNNING", "COMPLETED", "DONE", "CANCELLED"}


def _check_status(status):
    s = (status or "PLANNED").strip().upper()
    if s not in RUN_STATUSES:
        raise HTTPException(status_code=422, detail=f"Unknown production status '{status}'. Use one of {sorted(RUN_STATUSES)}.")
    return s


def _check_quantity(value, label):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise HTTPException(status_code=422, detail=f"{label} must be a non-negative whole number.")
    if value < 0:
        raise HTTPException(status_code=422, detail=f"{label} must be a non-negative whole number.")
    return value


def _check_quantities(target, completed):
    if target is not None and target > 0 and completed is not None and completed > target:
        raise HTTPException(status_code=422, detail=f"quantity_completed ({completed}) must not exceed quantity_target ({target}).")


def _visible_record(db, model, record_id, what):
    """Fetch a linked row through the scoped session.

    The ORM factory scoping (backend/db/scoping.py) already filters SELECTs,
    so a row from another company reads as not-found. Report every miss as a
    generic 404 without leaking whether the id exists elsewhere.
    """
    row = db.query(model).filter(model.id == record_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown {what}.")
    return row


def _validate_links(db, order_id, task_id, machine_id):
    from backend.models.models import Machine, Order, Task
    if order_id is not None:
        _visible_record(db, Order, order_id, "order")
    if task_id is not None:
        _visible_record(db, Task, task_id, "task")
    if machine_id is not None:
        _visible_record(db, Machine, machine_id, "machine")


def _derive_order_from_task(db, task_id):
    """Task-centric link: a run filed under a task inherits its order.

    Only fills a missing order_id; an explicitly supplied order is never
    overwritten (backward compatible with existing loosely-linked rows).
    Cross-factory tasks already 404 in _validate_links, so derivation only
    ever sees same-factory tasks.
    """
    from backend.models.models import Task
    if task_id is None:
        return None
    task = db.query(Task).filter(Task.id == task_id).first()
    if task is None:
        return None
    return task.order_id


@router.post("", response_model=ProductionRunResponse)
def create_production(production: ProductionRunCreate, db: Session = Depends(get_db)):
    data = production.model_dump()
    data["status"] = _check_status(data.get("status"))
    data["quantity_target"] = _check_quantity(data.get("quantity_target"), "quantity_target")
    data["quantity_completed"] = _check_quantity(data.get("quantity_completed"), "quantity_completed")
    _check_quantities(data.get("quantity_target"), data.get("quantity_completed"))
    _validate_links(db, data.get("order_id"), data.get("task_id"), data.get("machine_id"))
    if data.get("task_id") is not None and data.get("order_id") is None:
        data["order_id"] = _derive_order_from_task(db, data.get("task_id"))
    db_prod = ProductionRun(**data)
    db.add(db_prod)
    # Lifecycle propagation in the same transaction: runs -> task -> order.
    task = sync_task_completion(db, db_prod.task_id)
    if task is not None and task.order_id is not None:
        sync_order_completion(db, task.order_id)
    db.commit()
    db.refresh(db_prod)
    return db_prod

@router.get("", response_model=List[ProductionRunResponse])
def get_productions(
    status: Optional[str] = None,
    order_id: Optional[UUID] = None,
    machine_id: Optional[UUID] = None,
    db: Session = Depends(get_db)
):
    query = db.query(ProductionRun)
    if status: query = query.filter(ProductionRun.status == status.strip().upper())
    if order_id: query = query.filter(ProductionRun.order_id == order_id)
    if machine_id: query = query.filter(ProductionRun.machine_id == machine_id)
    return query.all()

@router.get("/{production_id}", response_model=ProductionRunResponse)
def get_production(production_id: UUID, db: Session = Depends(get_db)):
    db_prod = db.query(ProductionRun).filter(ProductionRun.id == production_id).first()
    if not db_prod:
        raise HTTPException(status_code=404, detail="Production run not found")
    return db_prod

@router.put("/{production_id}", response_model=ProductionRunResponse)
def update_production(production_id: UUID, production: ProductionRunUpdate, db: Session = Depends(get_db)):
    db_prod = db.query(ProductionRun).filter(ProductionRun.id == production_id).first()
    if not db_prod:
        raise HTTPException(status_code=404, detail="Production run not found")
    update_data = production.model_dump(exclude_unset=True)
    if "status" in update_data:
        update_data["status"] = _check_status(update_data["status"])
    if "quantity_target" in update_data:
        update_data["quantity_target"] = _check_quantity(update_data["quantity_target"], "quantity_target")
    if "quantity_completed" in update_data:
        update_data["quantity_completed"] = _check_quantity(update_data["quantity_completed"], "quantity_completed")
    for link_key in ("order_id", "task_id", "machine_id"):
        if link_key in update_data and update_data[link_key] is not None:
            _validate_links(
                db,
                update_data.get("order_id") if link_key == "order_id" else None,
                update_data.get("task_id") if link_key == "task_id" else None,
                update_data.get("machine_id") if link_key == "machine_id" else None,
            )
    effective_target = update_data.get("quantity_target", db_prod.quantity_target)
    effective_completed = update_data.get("quantity_completed", db_prod.quantity_completed)
    _check_quantities(effective_target, effective_completed)
    if update_data.get("task_id") is not None and "order_id" not in update_data:
        derived = _derive_order_from_task(db, update_data.get("task_id"))
        if derived is not None:
            update_data["order_id"] = derived
    for key, value in update_data.items():
        setattr(db_prod, key, value)
    # Lifecycle propagation in the same transaction: runs -> task -> order.
    task = sync_task_completion(db, db_prod.task_id)
    if task is not None and task.order_id is not None:
        sync_order_completion(db, task.order_id)
    db.commit()
    db.refresh(db_prod)
    return db_prod

@router.delete("/{production_id}")
def delete_production(production_id: UUID, db: Session = Depends(get_db)):
    db_prod = db.query(ProductionRun).filter(ProductionRun.id == production_id).first()
    if not db_prod:
        raise HTTPException(status_code=404, detail="Production run not found")
    db.delete(db_prod)
    db.commit()
    return {"message": "Production run deleted"}
