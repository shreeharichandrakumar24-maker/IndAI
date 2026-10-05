from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from backend.db.database import get_db

from backend.models.models import Employee, WorkerCredential
from backend.schemas.employee import EmployeeCreate, EmployeeUpdate, EmployeeResponse

router = APIRouter()

@router.post("", response_model=EmployeeResponse)
def create_employee(employee: EmployeeCreate, db: Session = Depends(get_db)):
    db_employee = Employee(**employee.model_dump())
    db.add(db_employee)
    db.commit()
    db.refresh(db_employee)
    return db_employee

@router.get("", response_model=List[EmployeeResponse])
def get_employees(status: Optional[str] = None, code: Optional[str] = None,
                  q: Optional[str] = None, db: Session = Depends(get_db)):
    """List employees. Optional ?code=EMP-001 (any spoken form: "emp 001",
    "employee one") and ?q= (name/role partial, case-insensitive).
    Backward compatible: no params behaves exactly as before. Never
    returns credentials (codes live in worker_credentials)."""
    from sqlalchemy import or_
    query = db.query(Employee)
    if status:
        query = query.filter(Employee.status == status)
    if code:
        from backend.services.resolve import normalize_employee_code
        norm = normalize_employee_code(code)
        if not norm:
            return []
        # Stored codes may be hyphenated (EMP-001) or compact (EMP001).
        cands = list(dict.fromkeys([norm, norm.replace("-", "")]))
        query = query.join(WorkerCredential,
                           WorkerCredential.employee_id == Employee.id).filter(
            WorkerCredential.employee_code.in_(cands))
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(Employee.name.ilike(like), Employee.role.ilike(like)))
    return query.all()

@router.get("/{employee_id}", response_model=EmployeeResponse)
def get_employee(employee_id: UUID, db: Session = Depends(get_db)):
    db_employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not db_employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    return db_employee

@router.put("/{employee_id}", response_model=EmployeeResponse)
def update_employee(employee_id: UUID, employee: EmployeeUpdate, db: Session = Depends(get_db)):
    db_employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not db_employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    update_data = employee.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_employee, key, value)
    db.commit()
    db.refresh(db_employee)
    return db_employee

@router.delete("/{employee_id}")
def delete_employee(employee_id: UUID, db: Session = Depends(get_db)):
    db_employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not db_employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    db.delete(db_employee)
    db.commit()
    return {"message": "Employee deleted"}


def _next_code_and_email(db, employee):
    from sqlalchemy import func as _func
    max_code = 0
    for (code,) in db.query(WorkerCredential.employee_code).all():
        if code and code.startswith("EMP-"):
            try:
                max_code = max(max_code, int(code[4:]))
            except ValueError:
                pass
    code = f"EMP-{max_code + 1:03d}"
    parts = (employee.name or "").lower().split()
    base = f"{parts[0]}.{parts[-1]}" if len(parts) > 1 else (parts[0] if parts else "worker")
    taken = {e.lower() for (e,) in db.query(WorkerCredential.email).all() if e}
    email, i = f"{base}@indai-factory.example", 1
    while email in taken:
        i += 1
        email = f"{base}{i}@indai-factory.example"
    taken_u = {u for (u,) in db.query(WorkerCredential.username).all()}
    uname, j = base, 1
    while uname in taken_u:
        j += 1
        uname = f"{base}{j}"
    return code, email, uname


@router.get("/{employee_id}/worker-login")
def get_worker_login(employee_id: UUID, db: Session = Depends(get_db)):
    db_employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not db_employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    cred = db.query(WorkerCredential).filter(WorkerCredential.employee_id == employee_id).first()
    if cred is None:
        return {"has_login": False, "employee_code": None, "email": None, "username": None}
    return {"has_login": True, "employee_code": cred.employee_code,
            "email": cred.email, "username": cred.username}


@router.post("/{employee_id}/worker-login")
def create_worker_login(employee_id: UUID, body: dict, db: Session = Depends(get_db)):
    import secrets
    from backend.services.worker_auth import hash_password
    db_employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not db_employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    if db.query(WorkerCredential).filter(WorkerCredential.employee_id == employee_id).first():
        raise HTTPException(status_code=409, detail="Login already exists. Use reset.")
    email = str((body or {}).get("email") or "").strip().lower()
    code, suggested_email, uname = _next_code_and_email(db, db_employee)
    if email:
        clash = db.query(WorkerCredential).filter(WorkerCredential.email.ilike(email)).first()
        if clash:
            raise HTTPException(status_code=422, detail="Email already used.")
    else:
        email = suggested_email
    temp = "Temp-" + secrets.token_urlsafe(9)
    cred = WorkerCredential(employee_id=employee_id, username=uname,
                            password_hash=hash_password(temp), email=email,
                            employee_code=code, must_change_password=True)
    db.add(cred)
    db.commit()
    # temp password returned ONCE here; never stored or logged in plaintext.
    return {"username": uname, "employee_code": code, "email": email, "temp_password": temp}


@router.post("/{employee_id}/worker-login/reset")
def reset_worker_login(employee_id: UUID, db: Session = Depends(get_db)):
    import secrets
    from backend.services.worker_auth import hash_password
    cred = db.query(WorkerCredential).filter(WorkerCredential.employee_id == employee_id).first()
    if cred is None:
        raise HTTPException(status_code=404, detail="No login for this employee.")
    temp = "Temp-" + secrets.token_urlsafe(9)
    cred.password_hash = hash_password(temp)
    cred.must_change_password = True
    db.commit()
    return {"username": cred.username, "employee_code": cred.employee_code,
            "email": cred.email, "temp_password": temp}
