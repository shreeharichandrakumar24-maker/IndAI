"""Import endpoints (Phase C). Prefix /import.

Safety contract: analyze + preview only parse and validate in memory and
never write to the database. Only confirm (and its legacy alias commit)
insert rows — in a single transaction, stamped to the currently selected
factory via the X-Factory-Id header (same requirement as onboarding).
"""
import json
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.db.scoping import SCOPE_KEY
from backend.services.importer import (
    TARGET_FIELDS,
    TARGETS,
    describe_mapping,
    parse_file,
    propose_mapping,
    run_import_confirm,
    run_import_preview,
)

router = APIRouter()


def _check_target(target: str) -> str:
    t = (target or "").strip().lower()
    if t not in TARGETS:
        raise HTTPException(status_code=422, detail=f"Unknown target '{target}'. Use one of {list(TARGETS)}.")
    return t


def _require_factory(db: Session):
    scope = db.info.get(SCOPE_KEY)
    if not scope:
        raise HTTPException(status_code=400, detail="No active factory. Send the X-Factory-Id header.")
    return scope


def _confirmed_mapping(target: str, mapping: str) -> dict:
    try:
        confirmed = json.loads(mapping)
        if not isinstance(confirmed, dict):
            raise ValueError("mapping must be a JSON object")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Invalid mapping JSON: {e}")
    # Reject unknown target fields. Never accept factory_id from the client.
    allowed = set(TARGET_FIELDS[target])
    for src, fld in confirmed.items():
        if fld is not None and fld not in allowed:
            raise HTTPException(status_code=422, detail=f"Unknown target field '{fld}' for '{target}'.")
    return confirmed


async def _parse_upload(target: str, file: UploadFile):
    content = await file.read()
    try:
        return parse_file(file.filename or "", content)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/analyze")
async def analyze_import(target: str = Form(...), file: UploadFile = File(...)):
    """Parse the file + propose a column mapping. Reads nothing, writes nothing."""
    t = _check_target(target)
    headers, rows = await _parse_upload(t, file)
    samples = rows[:5]
    # Send ONLY headers + up to 5 sample rows to the LLM.
    mapping, confidence, source = propose_mapping(t, headers, samples)
    details, warnings = describe_mapping(t, headers, mapping, confidence, source)
    if not rows:
        warnings = ["No data rows found — nothing to import."] + warnings
    unmapped = [h for h in headers if not mapping.get(h)]
    return {
        "target": t,
        "filename": file.filename,
        "row_count": len(rows),
        "source_columns": headers,
        "sample_rows": samples,
        "proposed_mapping": details,
        "mapped_count": sum(1 for h in headers if mapping.get(h)),
        "unmapped_columns": unmapped,
        "warnings": warnings,
        "errors": [],
        # Legacy keys kept for the existing Import page.
        "headers": headers,
        "target_fields": TARGET_FIELDS[t],
        "mapping": mapping,
        "confidence": confidence,
        "source": source,  # "ai" | "rule-based"
    }


@router.post("/preview")
async def preview_import(
    target: str = Form(...),
    mapping: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Validate every row against the confirmed mapping. Reads only — never writes."""
    t = _check_target(target)
    _require_factory(db)
    confirmed = _confirmed_mapping(t, mapping)
    headers, rows = await _parse_upload(t, file)
    out = run_import_preview(db, t, rows, confirmed)
    out["filename"] = file.filename
    out["source_columns"] = headers
    return out


def _do_confirm(db: Session, target: str, mapping: str, headers, rows) -> dict:
    _require_factory(db)
    confirmed = _confirmed_mapping(target, mapping)
    return run_import_confirm(db, target, rows, confirmed)


@router.post("/confirm")
async def confirm_import(
    target: str = Form(...),
    mapping: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Validate everything again, then insert in one transaction. The ONLY writer."""
    t = _check_target(target)
    headers, rows = await _parse_upload(t, file)
    return _do_confirm(db, t, mapping, headers, rows)


@router.post("/commit")
async def commit_import(
    target: str = Form(...),
    mapping: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Legacy alias of /confirm (kept for the existing Import page)."""
    t = _check_target(target)
    headers, rows = await _parse_upload(t, file)
    return _do_confirm(db, t, mapping, headers, rows)
