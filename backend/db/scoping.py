"""Per-request factory (company) scoping.

The selected company travels to the backend in the ``X-Factory-Id`` header.
:func:`resolve_factory_scope` (a FastAPI dependency) resolves that id to a
``factory_profile`` row and stores a small descriptor on the request's
SQLAlchemy ``Session`` (``session.info["factory_scope"]``). Two ``Session``
events then do the isolation work:

* ``do_orm_execute`` — every SELECT for a :data:`SCOPED_MODELS` entity is
  wrapped with ``with_loader_criteria`` so reads only return the selected
  company's rows.
* ``before_flush`` — newly inserted scoped rows get ``factory_id`` stamped
  from the active scope.

No header -> no scope -> exact legacy behavior (the original single-factory
app). The DEFAULT / LEGACY company (``factory_profile.is_default = true``)
additionally sees rows whose ``factory_id IS NULL``, so all pre-existing data
keeps working untouched. Any other company only sees rows explicitly tagged
with its own id — Company A can never read Company B's data.
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session, with_loader_criteria
from sqlalchemy import event

from backend.db.database import get_db
from backend.models.models import FactoryProfile, SCOPED_MODELS

SCOPE_KEY = "factory_scope"


def get_scope(db: Session) -> Optional[Dict[str, Any]]:
    """Active scope descriptor on this session, or None (legacy behavior)."""
    try:
        return db.info.get(SCOPE_KEY)
    except Exception:
        return None


def current_factory_id(db: Session) -> Optional[UUID]:
    scope = get_scope(db)
    return scope.get("uuid") if scope else None


def _criteria(scope: Dict[str, Any]):
    fid = scope["uuid"]
    if scope.get("include_null"):
        return lambda cls: or_(cls.factory_id == fid, cls.factory_id.is_(None))
    return lambda cls: cls.factory_id == fid


@event.listens_for(Session, "do_orm_execute")
def _scope_selects(execute_state) -> None:
    if not execute_state.is_select:
        return
    db = execute_state.session
    scope = get_scope(db)
    if not scope:
        return
    try:
        stmt = execute_state.statement
        crit = _criteria(scope)
        for model in SCOPED_MODELS:
            stmt = stmt.options(with_loader_criteria(model, crit, include_aliases=True))
        execute_state.statement = stmt
    except Exception:
        # Never break a query because scoping metadata was unexpected.
        return


@event.listens_for(Session, "before_flush")
def _stamp_inserts(session, flush_context, instances) -> None:
    scope = get_scope(session)
    if not scope:
        return
    fid = scope["uuid"]
    for obj in list(session.new):
        if isinstance(obj, SCOPED_MODELS) and getattr(obj, "factory_id", None) is None:
            obj.factory_id = fid


def resolve_factory_scope(request: Request, db: Session = Depends(get_db)) -> None:
    """FastAPI dependency: turn the X-Factory-Id header into a session scope.

    Missing header -> no scoping (backward compatible). Unknown id -> 404.
    A missing/unmigrated factory_profile table degrades to no scoping rather
    than breaking the API.
    """
    raw = request.headers.get("X-Factory-Id")
    if not raw:
        return
    try:
        fid = UUID(str(raw).strip())
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid X-Factory-Id header.")
    try:
        row = db.query(FactoryProfile).filter(FactoryProfile.id == fid).first()
    except Exception:
        # factory_profile table not migrated yet -> behave as before.
        return
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown factory. Pick a company again.")
    db.info[SCOPE_KEY] = {
        "id": str(row.id),
        "uuid": row.id,
        "include_null": bool(row.is_default),
    }


def set_factory_scope(db: Session, factory_id: UUID, include_null: bool) -> None:
    """Programmatic scope (used by onboarding/factory endpoints internally)."""
    db.info[SCOPE_KEY] = {"id": str(factory_id), "uuid": factory_id, "include_null": include_null}


def clear_factory_scope(db: Session) -> None:
    db.info.pop(SCOPE_KEY, None)
