"""Worker login (prototype). Prefix /worker-auth. No auth required.

POST /login {identifier} or legacy {username} + {password} -> {token,
employee{...}, must_change_password} or generic 401. Identifier may be
email, employee code or username (case-insensitive). Updates last_login_at.
Rate limited: 10 failures / identifier / 5 min -> 429.

POST /change-password {current_password, new_password} (token required,
min 8 chars): new scrypt hash, clears must_change_password.
"""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.models.models import Employee, WorkerCredential
from backend.services.worker_auth import (
    clear_failures,
    hash_password,
    mint_token,
    rate_limited,
    record_failure,
    verify_password,
    verify_token,
)

router = APIRouter()
bearer = HTTPBearer(auto_error=False)


class LoginBody(BaseModel):
    identifier: str | None = None
    username: str | None = None
    password: str = ""


class ChangeBody(BaseModel):
    current_password: str = ""
    new_password: str = ""


def _employee_payload(employee: Employee, cred: WorkerCredential) -> dict:
    return {
        "id": str(employee.id),
        "name": employee.name,
        "role": employee.role,
        "shift": employee.shift,
        "status": employee.status,
        "availability": employee.availability,
        "skills": employee.skills,
        "certifications": employee.certifications,
        "employee_code": cred.employee_code,
        "email": cred.email,
    }


def _find_credential(db: Session, identifier: str):
    key = (identifier or "").strip().lower()
    if not key:
        return None
    cred = db.query(WorkerCredential).filter(WorkerCredential.username == key).first()
    if cred is not None:
        return cred
    cred = db.query(WorkerCredential).filter(WorkerCredential.employee_code == key.upper()).first()
    if cred is not None:
        return cred
    return db.query(WorkerCredential).filter(func.lower(WorkerCredential.email) == key).first()


@router.post("/login")
def worker_login(body: LoginBody, db: Session = Depends(get_db)):
    from sqlalchemy.exc import ProgrammingError
    identifier = (body.identifier or body.username or "").strip()
    key = identifier.lower()
    if rate_limited(key):
        raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")
    try:
        cred = _find_credential(db, identifier)
        employee = None
        if cred is not None:
            employee = db.query(Employee).filter(Employee.id == cred.employee_id).first()
    except ProgrammingError:
        raise HTTPException(status_code=500, detail="worker_credentials table missing — run backend/db/migrations/006_worker_credentials.sql and 007_worker_auth_fields.sql first.")
    if cred is None or employee is None or not verify_password(body.password or "", cred.password_hash):
        record_failure(key)
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    clear_failures(key)
    cred.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return {"token": mint_token(str(employee.id)),
            "employee": _employee_payload(employee, cred),
            "must_change_password": bool(cred.must_change_password)}


def get_current_worker(db: Session = Depends(get_db),
                       creds: HTTPAuthorizationCredentials = Depends(bearer)):
    """Dependency: Bearer token -> (Employee, WorkerCredential). Any bad,
    expired or orphaned token is an identical 401. Shared by /worker/*. """
    token = creds.credentials if creds else ""
    eid = verify_token(token)
    employee = cred = None
    if eid:
        try:
            employee = db.query(Employee).filter(Employee.id == UUID(eid)).first()
        except (ValueError, AttributeError):
            employee = None
        if employee is not None:
            cred = db.query(WorkerCredential).filter(WorkerCredential.employee_id == employee.id).first()
    if employee is None or cred is None:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    return employee, cred


@router.post("/change-password")
def change_password(body: ChangeBody, db: Session = Depends(get_db),
                    current=Depends(get_current_worker)):
    employee, cred = current
    if not verify_password(body.current_password or "", cred.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    if len(body.new_password or "") < 8:
        raise HTTPException(status_code=422, detail="New password must be at least 8 characters.")
    cred.password_hash = hash_password(body.new_password)
    cred.must_change_password = False
    db.commit()
    return {"ok": True}
