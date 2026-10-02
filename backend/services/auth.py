"""Supabase Auth token verification (Phase 1).

No service key needed: the user's own access token is validated by calling
Supabase Auth's GET /auth/v1/user, which returns the user only when the
token is genuine. Needs SUPABASE_URL + SUPABASE_ANON_KEY (publishable).
"""
from typing import Any, Dict

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.db.database import get_db

bearer = HTTPBearer(auto_error=False)

ROLES = ("MANAGER", "OPERATOR", "WORKER")


class AuthError(HTTPException):
    def __init__(self, detail: str = "Not authenticated"):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def verify_supabase_token(token: str) -> Dict[str, Any]:
    """Validate access token with Supabase; return {id, email}. 401 if bad."""
    if not settings.SUPABASE_URL or not settings.SUPABASE_ANON_KEY:
        raise AuthError("Auth not configured (SUPABASE_URL/ANON_KEY missing).")
    url = settings.SUPABASE_URL.rstrip("/") + "/auth/v1/user"
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, headers={
                "Authorization": f"Bearer {token}",
                "apikey": settings.SUPABASE_ANON_KEY,
            })
        if resp.status_code != 200:
            raise AuthError("Invalid or expired session. Please sign in again.")
        data = resp.json()
        if not data.get("id"):
            raise AuthError("Invalid session.")
        return {"id": data["id"], "email": data.get("email")}
    except AuthError:
        raise
    except Exception:
        raise AuthError("Authentication service unreachable. Try again.")


def dev_manager(db: Session):
    """DEV ONLY: shared local manager used when AUTH_DISABLED=true."""
    from backend.models.models import AppUser

    user = db.query(AppUser).filter(AppUser.supabase_uid == "local-dev").first()
    if user is None:
        user = AppUser(supabase_uid="local-dev", email="dev@local",
                       name="Local Dev", role="MANAGER", active=True)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
):
    """Resolve Bearer token -> AppUser row (auto-provision on first login).

    First-ever user becomes MANAGER (bootstrap); later users default to
    OPERATOR until a manager assigns a role. Inactive users get 403.
    When AUTH_DISABLED=true (local dev bypass), returns the dev manager.
    """
    if settings.AUTH_DISABLED:
        return dev_manager(db)
    if creds is None or not creds.credentials:
        raise AuthError("Sign-in required.")
    ident = verify_supabase_token(creds.credentials)
    return resolve_user(db, ident["id"], ident.get("email"))


def resolve_user(db: Session, supabase_uid: str, email=None):
    """Find-or-create AppUser. Shared by the dependency and the middleware."""
    from backend.models.models import AppUser

    user = db.query(AppUser).filter(AppUser.supabase_uid == supabase_uid).first()
    if user is None:
        is_first = db.query(AppUser).count() == 0
        user = AppUser(
            supabase_uid=supabase_uid,
            email=email,
            name=(email or "").split("@")[0] or "User",
            role="MANAGER" if is_first else "OPERATOR",
            active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    if not user.active:
        raise HTTPException(status_code=403, detail="Account deactivated. Contact a manager.")
    return user


def require_manager(user=Depends(get_current_user)):
    if user.role != "MANAGER":
        raise HTTPException(status_code=403, detail="Managers only.")
    return user


def require_operator(user=Depends(get_current_user)):
    if user.role not in ("MANAGER", "OPERATOR"):
        raise HTTPException(status_code=403, detail="Operators or managers only.")
    return user
