"""Natural-reference resolver (Part 2+3). ONE shared endpoint used by Jarvis
(voice), the text assistant and any future caller — no duplicated logic.

GET /api/resolve?type=task|order|incident|proposal|employee|machine|plan&q=...

Matches full ids, exact/partial names, order numbers, machine codes/names
(incl. spoken "M 001" / "M zero zero one"), skill+assignee combos
("welding task for Suresh") and employee codes/names ("EMP-001", "emp 001",
"employee one"). Returns {matches: [{type,id,label,summary}], ambiguous}.
Responses never contain email, username, password or hash.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.services.resolve import TYPES, resolve

router = APIRouter()


@router.get("")
def resolve_reference(type: str = Query(...), q: str = Query(...),
                      db: Session = Depends(get_db)):
    t = (type or "").strip().lower()
    if t not in TYPES:
        from fastapi import HTTPException
        raise HTTPException(status_code=422,
                            detail=f"Unknown type '{type}'. Use one of {list(TYPES)}.")
    return resolve(db, t, q or "")
