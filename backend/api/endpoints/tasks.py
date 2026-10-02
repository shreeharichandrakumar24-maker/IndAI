from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from backend.db.database import get_db

from backend.models.models import Task
from backend.schemas.task import TaskCreate, TaskUpdate, TaskResponse

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


@router.post("", response_model=TaskResponse)
def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    data = task.model_dump()
    data["status"] = _check_status(data.get("status"), db)
    db_task = Task(**data)
    db.add(db_task)
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
    if status: query = query.filter(Task.status == status)
    if priority: query = query.filter(Task.priority == priority)
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
    for key, value in update_data.items():
        setattr(db_task, key, value)
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
