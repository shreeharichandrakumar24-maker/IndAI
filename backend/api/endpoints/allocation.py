"""Allocation candidates (Part B). Prefix /allocation."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.services.allocation import allocation_candidates

router = APIRouter()


@router.get("/candidates")
def get_candidates(task_id: UUID, db: Session = Depends(get_db)):
    try:
        return allocation_candidates(db, task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Task not found")
