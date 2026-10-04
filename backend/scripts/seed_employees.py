"""Seed 15 demo employees + worker_credentials (Part A).

Run:  python -m backend.scripts.seed_employees [--clean] [--force]
Uses backend SessionLocal directly (backend code only, no HTTP).

- Idempotent: matches existing employees by exact name; never duplicates,
  never touches non-demo employees.
- Skills use the EXACT preset skill names so allocation matching works.
- Credentials: username firstname.lastname (lowercase, deduped), demo
  passwords Worker@101..115. Hashes only in DB; the plain list goes ONLY to
  docs/demo_worker_credentials.txt (gitignored, 6-column merge via
  backend.scripts.cred_file - existing passwords never dropped, .bak backup
  first). Nothing printed to console. New rows carry employee_code/email so
  seed and backfill_worker_auth are safe in any order (never renumbered).
- --clean removes ONLY these 15 (by exact name) + credentials (cascade);
  refuses if a seeded employee still has tasks unless --force is given
  (then those tasks' employee_id is set to null, per schema SET NULL).
"""
import argparse
import sys

from backend.db.database import SessionLocal
from backend.models.models import Employee, Task, WorkerCredential
from backend.scripts.cred_file import merge_cred_file
from backend.services.worker_auth import hash_password

# name, role, skills(list), certifications(list), shift, status, availability
DEMO = [
    ("Arun Prakash", "CNC Operator", ["CNC operation", "Quality inspection"], ["ISO 9001"], "Morning (6-14)", "ACTIVE", "AVAILABLE"),
    ("Divya Nair", "CNC Operator", ["CNC operation"], [], "Evening (14-22)", "ACTIVE", "AVAILABLE"),
    ("Karthik Raja", "CNC Operator", ["CNC operation", "Maintenance"], [], "Night (22-6)", "ACTIVE", "AVAILABLE"),
    ("Suresh Kumar", "Welder", ["Welding"], ["Welding cert"], "Morning (6-14)", "ACTIVE", "AVAILABLE"),
    ("Meena Devi", "Welder", ["Welding", "Quality inspection"], [], "Evening (14-22)", "ACTIVE", "AVAILABLE"),
    ("Ravi Shankar", "Press Operator", ["Press operation"], ["Forklift"], "Morning (6-14)", "ACTIVE", "AVAILABLE"),
    ("Anita Rao", "Grinder Operator", ["Grinding", "Quality inspection"], [], "Evening (14-22)", "ACTIVE", "AVAILABLE"),
    ("Vikram Singh", "Robot Technician", ["Assembly", "Maintenance"], [], "Morning (6-14)", "ACTIVE", "AVAILABLE"),
    ("Priya Sharma", "Laser Operator", ["Laser operation"], [], "Evening (14-22)", "ACTIVE", "AVAILABLE"),
    ("Mohammed Ali", "Molding Technician", ["Molding"], [], "Night (22-6)", "ACTIVE", "AVAILABLE"),
    ("Deepak Joshi", "Maintenance Technician", ["Maintenance", "Grinding"], [], "Morning (6-14)", "ACTIVE", "AVAILABLE"),
    ("Kavitha Reddy", "Maintenance Technician", ["Maintenance", "Laser operation"], [], "Night (22-6)", "ACTIVE", "ON_LEAVE"),
    ("Sanjay Patel", "Quality Inspector", ["Quality inspection", "Molding"], ["ISO 9001"], "Morning (6-14)", "ACTIVE", "AVAILABLE"),
    ("Ramesh Iyer", "Shift Supervisor", ["Assembly", "Quality inspection"], [], "Evening (14-22)", "ACTIVE", "AVAILABLE"),
    ("Manoj Verma", "Assembly Fitter", ["Assembly", "Press operation"], [], "Night (22-6)", "ACTIVE", "BUSY"),
]

CRED_FILE = "docs/demo_worker_credentials.txt"  # see backend.scripts.cred_file
DOMAIN = "indai-factory.example"


def username_for(name: str, taken: set) -> str:
    parts = name.lower().split()
    base = f"{parts[0]}.{parts[-1]}" if len(parts) > 1 else parts[0]
    u, i = base, 1
    while u in taken:
        i += 1
        u = f"{base}{i}"
    taken.add(u)
    return u


def email_for(name: str, taken: set) -> str:
    parts = name.lower().split()
    base = f"{parts[0]}.{parts[-1]}" if len(parts) > 1 else parts[0]
    e, i = f"{base}@{DOMAIN}", 1
    while e in taken:
        i += 1
        e = f"{base}{i}@{DOMAIN}"
    taken.add(e)
    return e


def seed() -> dict:
    db = SessionLocal()
    try:
        existing = {e.name: e for e in db.query(Employee).all()}
        taken = {c.username for c in db.query(WorkerCredential.username).all()}
        taken_e = {(c.email or "").lower() for c in db.query(WorkerCredential).all() if c.email}
        max_code = 0
        for c in db.query(WorkerCredential).all():
            if c.employee_code and c.employee_code.startswith("EMP-"):
                try:
                    max_code = max(max_code, int(c.employee_code[4:]))
                except ValueError:
                    pass
        created_emp = created_cred = filled = skipped = 0
        lines = []
        for idx, (name, role, skills, certs, shift, status, avail) in enumerate(DEMO, start=101):
            emp = existing.get(name)
            if emp is None:
                emp = Employee(name=name, role=role,
                               skills={"items": skills},
                               certifications={"items": certs} if certs else None,
                               shift=shift, status=status, availability=avail)
                db.add(emp)
                db.flush()
                created_emp += 1
            else:
                skipped += 1
            cred = db.query(WorkerCredential).filter(WorkerCredential.employee_id == emp.id).first()
            pwd = ""
            if cred is None:
                max_code += 1
                uname = username_for(name, taken)
                email = email_for(name, taken_e)
                pwd = f"Worker@{idx}"
                db.add(WorkerCredential(employee_id=emp.id, username=uname,
                                        password_hash=hash_password(pwd),
                                        email=email,
                                        employee_code=f"EMP-{max_code:03d}",
                                        must_change_password=False))
                created_cred += 1
            else:
                # Safe in any order vs backfill: fill fields an older seed
                # left blank, never renumber or overwrite what exists.
                if not cred.employee_code:
                    max_code += 1
                    cred.employee_code = f"EMP-{max_code:03d}"
                    filled += 1
                if not cred.email:
                    cred.email = email_for(name, taken_e)
                    filled += 1
            cred = db.query(WorkerCredential).filter(WorkerCredential.employee_id == emp.id).first()
            lines.append((name, role, cred.employee_code or "", cred.email or "",
                          cred.username, pwd))
        db.commit()
        # Merge-only (never drops existing plaintext; backs up to .bak first).
        file_info = merge_cred_file(lines)
        return {"created_employees": created_emp, "created_credentials": created_cred,
                "filled_fields": filled, "skipped_existing": skipped,
                "cred_file_rows": file_info["rows"],
                "preserved_passwords": file_info["preserved_passwords"]}
    finally:
        db.close()


def clean(force: bool) -> dict:
    db = SessionLocal()
    try:
        names = [d[0] for d in DEMO]
        emps = db.query(Employee).filter(Employee.name.in_(names)).all()
        busy = []
        for e in emps:
            n = db.query(Task).filter(Task.employee_id == e.id).count()
            if n:
                busy.append((e.name, n))
        if busy and not force:
            return {"refused": busy}
        for e in emps:
            if force:
                db.query(Task).filter(Task.employee_id == e.id).update({"employee_id": None})
            db.query(WorkerCredential).filter(WorkerCredential.employee_id == e.id).delete()
            db.delete(e)
        db.commit()
        return {"removed": len(emps)}
    finally:
        db.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if args.clean:
        print(clean(args.force))
    else:
        print(seed())
    return 0


if __name__ == "__main__":
    sys.exit(main())
