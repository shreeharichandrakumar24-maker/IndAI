"""Backfill worker auth fields (Part 1). Idempotent, additive only.

- Every employee gets a credentials row (existing rows untouched).
- employee_code = EMP-001, ... by employee created_at order, never renumbered.
- email = firstname.lastname@indai-factory.example (lowercase, deduped).
- username unchanged for existing rows; generated for the rest.
- Passwords: ONLY new credentials get a fresh demo password; existing
  password hashes are never touched.
- Merges into docs/demo_worker_credentials.txt (gitignored) via
  backend.scripts.cred_file (backs up to .txt.bak first, never drops
  existing plaintext passwords). Prints counts only.

Run:  python -m backend.scripts.backfill_worker_auth
"""
import sys

from backend.db.database import SessionLocal
from backend.models.models import Employee, WorkerCredential
from backend.scripts.cred_file import merge_cred_file
from backend.services.worker_auth import hash_password

DOMAIN = "indai-factory.example"


def _uname(name: str, taken: set) -> str:
    parts = name.lower().split()
    base = f"{parts[0]}.{parts[-1]}" if len(parts) > 1 else parts[0]
    u, i = base, 1
    while u in taken:
        i += 1
        u = f"{base}{i}"
    taken.add(u)
    return u


def _email(name: str, taken: set) -> str:
    parts = name.lower().split()
    base = f"{parts[0]}.{parts[-1]}" if len(parts) > 1 else parts[0]
    e, i = f"{base}@{DOMAIN}", 1
    while e in taken:
        i += 1
        e = f"{base}{i}@{DOMAIN}"
    taken.add(e)
    return e


def main() -> int:
    db = SessionLocal()
    try:
        employees = db.query(Employee).order_by(Employee.created_at).all()
        creds = {c.employee_id: c for c in db.query(WorkerCredential).all()}
        taken_u = {c.username for c in creds.values()}
        taken_e = {(c.email or "").lower() for c in creds.values() if c.email}
        max_code = 0
        for c in creds.values():
            if c.employee_code and c.employee_code.startswith("EMP-"):
                try:
                    max_code = max(max_code, int(c.employee_code[4:]))
                except ValueError:
                    pass
        created = filled = 0
        rows = []
        for emp in employees:
            cred = creds.get(emp.id)
            if cred is None:
                max_code += 1
                uname = _uname(emp.name, taken_u)
                email = _email(emp.name, taken_e)
                pwd = f"Worker@{100 + max_code}"
                cred = WorkerCredential(
                    employee_id=emp.id, username=uname, password_hash=hash_password(pwd),
                    email=email, employee_code=f"EMP-{max_code:03d}",
                    must_change_password=False)
                db.add(cred)
                db.flush()
                created += 1
                rows.append((emp.name, emp.role, cred.employee_code, email, uname, pwd))
            else:
                changed = False
                if not cred.employee_code:
                    max_code += 1
                    cred.employee_code = f"EMP-{max_code:03d}"
                    changed = True
                if not cred.email:
                    cred.email = _email(emp.name, taken_e)
                    changed = True
                if changed:
                    filled += 1
                rows.append((emp.name, emp.role or "", cred.employee_code or "",
                             cred.email or "", cred.username, ""))
        db.commit()
        file_info = merge_cred_file(rows)
        print({"new_credentials": created, "backfilled_fields": filled,
               "total_employees": len(employees),
               "cred_file_rows": file_info["rows"],
               "preserved_passwords": file_info["preserved_passwords"]})
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
