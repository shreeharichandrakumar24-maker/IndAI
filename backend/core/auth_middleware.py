"""API-wide authentication + role policy (Phase 1).

One place for the whole access scheme so endpoint files stay untouched:

- Open (no token): /api/health*, POST /api/telemetry (simulator ingest path),
  /, /docs, /openapi.json.
  - Worker prototype (own HMAC Bearer check, NOT Supabase):
    exactly POST /api/worker-auth/login is public; every route starting
    with "/api/worker/" (trailing slash) plus POST /api/worker-auth/change-password
    skips the Supabase check and relies on get_current_worker.
- Everything else: valid Supabase Bearer token required (401 otherwise).
- Roles: MANAGER > OPERATOR > WORKER (see services/auth.py).
  - GET: any authenticated user.
  - POST/PUT/PATCH: OPERATOR or MANAGER, except PUT /api/tasks* which any
    authenticated role may call (workers update task progress; mobile later).
  - MANAGER only: all DELETEs, /api/users*, POST /api/profile/approve,
    */decision (AI recommendation approvals).

Resolved user is attached to request.state.user for endpoint use.
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.db.database import SessionLocal
from backend.services.auth import AuthError, resolve_user, verify_supabase_token


def _min_role(method: str, path: str):
    if path.startswith("/api/users") or path.endswith("/decision") or (
        method == "POST" and path.rstrip("/") == "/api/profile/approve"
    ):
        return "MANAGER"
    if path.startswith("/api/assignments/") and path.endswith("/pair"):
        return "MANAGER"  # applying a pairing is a manager decision
    if method == "DELETE" and path.startswith("/api/"):
        return "MANAGER"
    if method in ("POST", "PUT", "PATCH") and path.startswith("/api/"):
        if method == "PUT" and path.startswith("/api/tasks"):
            return None  # any authenticated role (worker progress updates)
        if path.startswith("/api/assignments"):
            return None  # workers advance their own assignments (row-checked)
        if path.startswith("/api/push-tokens"):
            return None  # every login registers its own device token
        return "OPERATOR"
    return None  # GET and anything else: any authenticated user


_RANK = {"WORKER": 1, "OPERATOR": 2, "MANAGER": 3}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # DEV ONLY bypass: everything open, acting as the local dev manager.
        from backend.core.config import settings
        if settings.AUTH_DISABLED:
            db = SessionLocal()
            try:
                from backend.services.auth import dev_manager
                request.state.user = dev_manager(db)
            finally:
                db.close()
            return await call_next(request)
        # Open paths: docs, root, health, simulator ingest.
        if (
            path in ("/", "/docs", "/openapi.json")
            or path.startswith("/docs/")
            or path == "/api/health"
            or path.startswith("/api/health/")
            or (request.method == "POST" and path.rstrip("/") == "/api/telemetry")
        ):
            return await call_next(request)

        # Worker prototype auth: public login + own-token routes bypass Supabase.
        # Precise matches only: exactly POST /api/worker-auth/login public;
        # routes starting with "/api/worker/" (trailing slash) plus the
        # change-password route below use get_current_worker instead.
        if request.method == "POST" and path.rstrip("/") == "/api/worker-auth/login":
            return await call_next(request)
        if path.startswith("/api/worker/"):
            return await call_next(request)
        if request.method == "POST" and path.rstrip("/") == "/api/worker-auth/change-password":
            return await call_next(request)

        if not path.startswith("/api/"):
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        if not token:
            return JSONResponse(status_code=401, content={"detail": "Sign-in required."})
        try:
            ident = verify_supabase_token(token)
        except AuthError as e:
            return JSONResponse(status_code=e.status_code, content={"detail": e.detail})

        db = SessionLocal()
        try:
            try:
                user = resolve_user(db, ident["id"], ident.get("email"))
            except Exception as e:
                code = getattr(e, "status_code", 403)
                return JSONResponse(status_code=code, content={"detail": getattr(e, "detail", "Forbidden.")})
            need = _min_role(request.method, path)
            if need and _RANK.get(user.role, 0) < _RANK[need]:
                return JSONResponse(
                    status_code=403,
                    content={"detail": f"{need.title()}s only."},
                )
            request.state.user = user
        finally:
            db.close()
        return await call_next(request)
