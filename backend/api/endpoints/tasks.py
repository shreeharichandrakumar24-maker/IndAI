from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from backend.db.database import get_db

from backend.models.models import Task
from backend.schemas.task import TaskCreate, TaskUpdate, TaskResponse
from backend.services.completion import reopen_order_if_needed, sync_order_completion

router = APIRouter()

# Permissive superset covering every status the app has ever used
# (PENDING default, IN_PROGRESS active, DONE/COMPLETED closed, CANCELLED).
# Blocks garbage strings while never breaking existing flows.
TASK_STATUSES = {"PENDING", "IN_PROGRESS", "DONE", "COMPLETED", "CANCELLED"}


def _check_status(status, db):
    s = (status or "PENDING").upper()
    if s not in TASK_STATUSES:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"Unknown task status '{status}'. Use one of {sorted(TASK_STATUSES)}.")
    return s


def _check_progress(progress):
    if progress is None:
        return None
    try:
        p = float(progress)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Progress must be a number 0.0 through 1.0.")
    if not 0.0 <= p <= 1.0:
        raise HTTPException(status_code=422, detail="Progress must be a number 0.0 through 1.0.")
    return p


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


def _validate_links(db, employee_id, machine_id, order_id):
    from backend.models.models import Employee, Machine, Order
    if employee_id is not None:
        _visible_record(db, Employee, employee_id, "employee")
    if machine_id is not None:
        _visible_record(db, Machine, machine_id, "machine")
    if order_id is not None:
        _visible_record(db, Order, order_id, "order")


@router.post("", response_model=TaskResponse)
def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    data = task.model_dump()
    data["status"] = _check_status(data.get("status"), db)
    if data.get("progress") is not None:
        data["progress"] = _check_progress(data.get("progress"))
    _validate_links(db, data.get("employee_id"), data.get("machine_id"), data.get("order_id"))
    if (data.get("status") or "").upper() in ("DONE", "COMPLETED"):
        data["progress"] = 1.0
    db_task = Task(**data)
    db.add(db_task)
    # New task under an order re-evaluates it: a COMPLETED order with fresh
    # open work returns to IN_PROGRESS; an all-closed order stays COMPLETED.
    if db_task.order_id is not None:
        reopen_order_if_needed(db, db_task.order_id)
        if (db_task.status or "").strip().upper() in ("DONE", "COMPLETED"):
            sync_order_completion(db, db_task.order_id)
    db.commit()
    db.refresh(db_task)
    return db_task

@router.get("", response_model=List[TaskResponse])
def get_tasks(
    status: Optional[str] = None, 
    priority: Optional[str] = None,
    employee_id: Optional[UUID] = None,
    machine_id: Optional[UUID] = None,
    order_id: Optional[UUID] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Task)
    if status: query = query.filter(Task.status == status.strip().upper())
    if priority: query = query.filter(Task.priority == priority.strip().upper())
    if employee_id: query = query.filter(Task.employee_id == employee_id)
    if machine_id: query = query.filter(Task.machine_id == machine_id)
    if order_id: query = query.filter(Task.order_id == order_id)
    return query.all()

@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: UUID, db: Session = Depends(get_db)):
    db_task = db.query(Task).filter(Task.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    return db_task

@router.put("/{task_id}", response_model=TaskResponse)
def update_task(task_id: UUID, task: TaskUpdate, db: Session = Depends(get_db)):
    db_task = db.query(Task).filter(Task.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    update_data = task.model_dump(exclude_unset=True)
    if "status" in update_data:
        update_data["status"] = _check_status(update_data["status"], db)
    if "progress" in update_data:
        update_data["progress"] = _check_progress(update_data["progress"])
    for link_key in ("employee_id", "machine_id", "order_id"):
        if link_key in update_data and update_data[link_key] is not None:
            _validate_links(
                db,
                update_data.get("employee_id") if link_key == "employee_id" else None,
                update_data.get("machine_id") if link_key == "machine_id" else None,
                update_data.get("order_id") if link_key == "order_id" else None,
            )
    previous_order_id = db_task.order_id
    for key, value in update_data.items():
        setattr(db_task, key, value)
    if (db_task.status or "").upper() in ("DONE", "COMPLETED"):
        db_task.progress = 1.0
    # Re-evaluate both sides of a move: the previous order may reopen, the
    # current order may reopen (fresh open work) or complete (all closed).
    if previous_order_id is not None and previous_order_id != db_task.order_id:
        reopen_order_if_needed(db, previous_order_id)
    if db_task.order_id is not None:
        reopen_order_if_needed(db, db_task.order_id)
        if (db_task.status or "").strip().upper() in ("DONE", "COMPLETED"):
            sync_order_completion(db, db_task.order_id)
    db.commit()
    db.refresh(db_task)
    return db_task

@router.delete("/{task_id}")
def delete_task(task_id: UUID, db: Session = Depends(get_db)):
    db_task = db.query(Task).filter(Task.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(db_task)
    db.commit()
    return {"message": "Task deleted"}
