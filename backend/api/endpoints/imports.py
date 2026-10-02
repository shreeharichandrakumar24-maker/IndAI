"""Import endpoints (Phase C). Prefix /import."""
import json
import re
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.models.models import Employee, Machine, MachineTelemetry, Order
from backend.services.importer import (
    TARGET_FIELDS,
    TARGETS,
    build_validated_row,
    parse_file,
    propose_mapping,
)

router = APIRouter()


def _check_target(target: str) -> str:
    t = (target or "").strip().lower()
    if t not in TARGETS:
        raise HTTPException(status_code=422, detail=f"Unknown target '{target}'. Use one of {list(TARGETS)}.")
    return t


@router.post("/analyze")
async def analyze_import(target: str = Form(...), file: UploadFile = File(...)):
    t = _check_target(target)
    content = await file.read()
    try:
        headers, rows = parse_file(file.filename or "", content)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    samples = rows[:5]
    # Send ONLY headers + up to 5 sample rows to the LLM.
    mapping, confidence, source = propose_mapping(t, headers, samples)
    return {
        "target": t,
        "filename": file.filename,
        "headers": headers,
        "row_count": len(rows),
        "sample_rows": samples,
        "target_fields": TARGET_FIELDS[t],
        "mapping": mapping,
        "confidence": confidence,
        "source": source,  # "ai" | "rule-based"
    }


@router.post("/commit")
async def commit_import(
    target: str = Form(...),
    mapping: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    t = _check_target(target)
    try:
        confirmed = json.loads(mapping)
        if not isinstance(confirmed, dict):
            raise ValueError("mapping must be a JSON object")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Invalid mapping JSON: {e}")
    # Reject unknown target fields.
    allowed = set(TARGET_FIELDS[t])
    for src, fld in confirmed.items():
        if fld is not None and fld not in allowed:
            raise HTTPException(status_code=422, detail=f"Unknown target field '{fld}' for '{t}'.")

    content = await file.read()
    try:
        headers, rows = parse_file(file.filename or "", content)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Preload lookups for dedup + machine resolution.
    machines = db.query(Machine).all()
    code_to_id = {}
    name_to_id = {}
    for m in machines:
        name_to_id[(m.name or "").strip().lower()] = m.id
        mm = re.match(r"^(M-\d{3})", (m.name or "").strip())
        if mm:
            code_to_id[mm.group(1).upper()] = m.id
    existing_orders = {o.order_number for o in db.query(Order.order_number).all()} if t == "orders" else set()
    existing_machine_names = {m.name for m in machines} if t == "machines" else set()
    existing_machine_codes = set(code_to_id) if t == "machines" else set()
    existing_employees = (
        {(e.name, e.role) for e in db.query(Employee.name, Employee.role).all()} if t == "employees" else set()
    )

    inserted = 0
    skipped_duplicates = 0
    failed = 0
    errors: list = []
    seen_orders_in_file = set()

    def resolve_machine_id(mapped: dict) -> tuple:
        """Returns (uuid|None, error|None) for telemetry rows."""
        raw = mapped.get("machine_code", mapped.get("machine_id"))
        # mapping may target machine_id directly with a UUID or a code/name string
        if isinstance(raw, str):
            s = raw.strip()
        elif raw is None:
            return None, "missing machine reference (machine_code)"
        else:
            s = str(raw)
        su = s.upper()
        if su in code_to_id:
            return code_to_id[su], None
        m = re.match(r"^(M-\d{3})", s.strip(), re.IGNORECASE)
        if m and m.group(1).upper() in code_to_id:
            return code_to_id[m.group(1).upper()], None
        if s.strip().lower() in name_to_id:
            return name_to_id[s.strip().lower()], None
        return None, f"unknown machine '{s}'"

    for idx, raw_row in enumerate(rows, start=2):  # 1-based + header
        mapped = {}
        for src_col, fld in confirmed.items():
            if fld:
                mapped[fld] = raw_row.get(src_col)
        # Telemetry: resolve machine_code/name -> machine_id.
        if t == "telemetry":
            if "machine_id" not in mapped or mapped.get("machine_id") in (None, ""):
                mid, err = resolve_machine_id({**mapped, "machine_code": mapped.get("machine_code")})
                if err:
                    failed += 1
                    if len(errors) < 20:
                        errors.append({"row": idx, "error": err})
                    continue
                mapped["machine_id"] = mid
            else:
                # machine_id given: accept UUID, else try code/name resolution
                try:
                    from uuid import UUID as _UUID
                    _UUID(str(mapped["machine_id"]))
                except ValueError:
                    mid, err = resolve_machine_id({"machine_code": mapped["machine_id"]})
                    if err:
                        failed += 1
                        if len(errors) < 20:
                            errors.append({"row": idx, "error": err})
                        continue
                    mapped["machine_id"] = mid
            mapped.pop("machine_code", None)

        obj, err = build_validated_row(t, mapped)
        if err or obj is None:
            failed += 1
            if len(errors) < 20:
                errors.append({"row": idx, "error": err or "validation failed"})
            continue

        # Upsert-skip duplicates.
        try:
            if t == "orders":
                if obj.order_number in existing_orders or obj.order_number in seen_orders_in_file:
                    skipped_duplicates += 1
                    continue
                seen_orders_in_file.add(obj.order_number)
                db.add(Order(**obj.model_dump()))
            elif t == "machines":
                code_m = re.match(r"^(M-\d{3})", (obj.name or "").strip())
                code = code_m.group(1).upper() if code_m else None
                if obj.name in existing_machine_names or (code and code in existing_machine_codes):
                    skipped_duplicates += 1
                    continue
                existing_machine_names.add(obj.name)
                if code:
                    existing_machine_codes.add(code)
                db.add(Machine(**obj.model_dump()))
            elif t == "employees":
                key = (obj.name, obj.role)
                if key in existing_employees:
                    skipped_duplicates += 1
                    continue
                existing_employees.add(key)
                db.add(Employee(**obj.model_dump()))
            elif t == "telemetry":
                # Historical rows: insert directly, never auto-create incidents.
                db.add(MachineTelemetry(**obj.model_dump()))
            inserted += 1
        except Exception as e:
            db.rollback()
            failed += 1
            if len(errors) < 20:
                errors.append({"row": idx, "error": str(e)})

    db.commit()
    return {
        "target": t,
        "inserted": inserted,
        "skipped_duplicates": skipped_duplicates,
        "failed": failed,
        "errors": errors[:20],
        "note": "Telemetry imports never auto-create incidents (historical rows)." if t == "telemetry" else None,
    }
