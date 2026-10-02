"""Factory memory timeline (Phase E). Prefix /memory."""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from sqlalchemy import or_

from backend.db.database import get_db
from backend.models.models import FactoryMemory, Incident
from backend.schemas.ai import MemoryResponse
from backend.services.auth import require_operator

router = APIRouter()


@router.get("", response_model=list[MemoryResponse])
def list_memory(
    machine_id: Optional[UUID] = None,
    order_id: Optional[UUID] = None,
    event_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(FactoryMemory).order_by(FactoryMemory.created_at.desc())
    if machine_id:
        q = q.filter(FactoryMemory.machine_id == machine_id)
    if order_id:
        q = q.filter(FactoryMemory.order_id == order_id)
    if event_type:
        q = q.filter(FactoryMemory.event_type == event_type)
    return q.limit(200).all()


class LogBody(BaseModel):
    title: str
    event_type: Optional[str] = None
    description: Optional[str] = None
    machine_id: Optional[UUID] = None
    order_id: Optional[UUID] = None
    task_id: Optional[UUID] = None
    resolution_action: Optional[str] = None
    # JSON key is "metadata_" (matches the Python column name; the Postgres
    # column itself is "metadata"). Kept explicit to avoid the reserved-name
    # collision that broke MemoryResponse before.
    metadata_: Optional[dict] = None

    model_config = ConfigDict(populate_by_name=True)


@router.post("/log", response_model=MemoryResponse)
def log_memory(body: LogBody, db: Session = Depends(get_db), user=Depends(require_operator)):
    """Explicit memory write for resolutions, simulation-applied actions, and
    other notable events. Frontend calls this AFTER the real action succeeds."""
    if not body.title.strip():
        raise HTTPException(status_code=422, detail="Title is required.")
    mem = FactoryMemory(
        title=body.title.strip()[:255],
        event_type=(body.event_type or "NOTE").upper()[:100],
        description=(body.description or "")[:2000] or None,
        machine_id=body.machine_id,
        order_id=body.order_id,
        task_id=body.task_id,
        resolution_action=(body.resolution_action or "")[:2000] or None,
        metadata_=body.metadata_,
    )
    db.add(mem)
    db.commit()
    db.refresh(mem)
    return mem


@router.get("/search", response_model=List[MemoryResponse])
def search_memory(q: str = "", event_type: Optional[str] = None,
                  machine_id: Optional[UUID] = None, order_id: Optional[UUID] = None,
                  limit: int = 50, db: Session = Depends(get_db)):
    """Keyword search across title/description/resolution_action + filters."""
    query = db.query(FactoryMemory).order_by(FactoryMemory.created_at.desc())
    needle = (q or "").strip()
    if needle:
        like = f"%{needle}%"
        query = query.filter(or_(
            FactoryMemory.title.ilike(like),
            FactoryMemory.description.ilike(like),
            FactoryMemory.resolution_action.ilike(like),
        ))
    if event_type:
        query = query.filter(FactoryMemory.event_type == event_type)
    if machine_id:
        query = query.filter(FactoryMemory.machine_id == machine_id)
    if order_id:
        query = query.filter(FactoryMemory.order_id == order_id)
    return query.limit(min(max(limit, 1), 200)).all()


@router.get("/similar", response_model=List[MemoryResponse])
def similar_memory(incident_id: Optional[UUID] = None, machine_id: Optional[UUID] = None,
                   order_id: Optional[UUID] = None, limit: int = 5,
                   db: Session = Depends(get_db)):
    """Past events for the same machine first, then same order, then recent."""
    mid, oid = machine_id, order_id
    if incident_id:
        inc = db.query(Incident).filter(Incident.id == incident_id).first()
        if inc is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        mid = mid or inc.machine_id
        oid = oid or inc.order_id
    if not mid and not oid:
        raise HTTPException(status_code=422, detail="Provide incident_id, machine_id or order_id.")
    ranked = []
    seen = set()
    for flt in ({"mid": mid}, {"oid": oid}):
        if flt.get("mid"):
            rows = db.query(FactoryMemory).filter(FactoryMemory.machine_id == flt["mid"]) \
                .order_by(FactoryMemory.created_at.desc()).limit(limit).all()
        elif flt.get("oid"):
            rows = db.query(FactoryMemory).filter(FactoryMemory.order_id == flt["oid"]) \
                .order_by(FactoryMemory.created_at.desc()).limit(limit).all()
        else:
            continue
        for r in rows:
            if r.id not in seen:
                seen.add(r.id)
                ranked.append(r)
        if len(ranked) >= limit:
            break
    return ranked[:limit]
