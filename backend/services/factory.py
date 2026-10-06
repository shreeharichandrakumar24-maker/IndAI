"""Factory / company registry + 8-step onboarding helpers.

One place for: onboarding state shape, section validation, legacy-compatible
threshold defaults, AI-preference enums and factory summary counts.

Onboarding state lives in ``factory_profile.onboarding`` (JSONB). The
validated operational data lives in the EXISTING tables (employees, machines,
orders, maintenance, ...) tagged with ``factory_id`` — no duplicate
"onboarding_*" models or tables are created.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from backend.models.models import (
    Employee,
    FactoryProfile,
    Machine,
    Maintenance,
    Order,
)

# ---------------------------------------------------------------------------
# Step / status vocabulary
# ---------------------------------------------------------------------------
STEP_KEYS = [
    "company",
    "employees",
    "machines",
    "production",
    "orders",
    "maintenance",
    "thresholds",
    "ai_preferences",
]

STEP_LABELS = {
    "company": "Company / Industry Profile",
    "employees": "Employees",
    "machines": "Machines / Equipment",
    "production": "Production",
    "orders": "Orders / Customers",
    "maintenance": "Maintenance History",
    "thresholds": "IoT / Machine Thresholds",
    "ai_preferences": "AI Preferences",
}

SECTION_PENDING = "PENDING"
SECTION_AVAILABLE = "AVAILABLE"
SECTION_NOT_AVAILABLE = "NOT_AVAILABLE"
SECTION_DEFAULT = "DEFAULT"

STATUS_DRAFT = "DRAFT"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_COMPLETE = "COMPLETE"

# Sections that must be resolved (available / not-available / default) before
# setup can be completed.
REQUIRED_SECTIONS = ["company", "machines", "thresholds", "ai_preferences"]

DEFAULT_THRESHOLDS = {
    "temp_max": 85.0,
    "vibration_max": 5.0,
    "current_max": 10.0,
    "rpm_min": 1300.0,
}

PRIMARY_PRIORITIES = [
    "PRODUCTION_CONTINUITY",
    "DELIVERY_DEADLINES",
    "MACHINE_HEALTH",
    "MAINTENANCE_COST",
    "PRODUCTION_COST",
    "QUALITY",
    "WORKFORCE_UTILIZATION",
    "CUSTOMER_PRIORITY",
]
RECOMMENDATION_STYLES = ["ACTIONABLE", "BALANCED", "DETAILED"]
RISK_TOLERANCES = ["CONSERVATIVE", "BALANCED", "AGGRESSIVE"]

DEFAULT_AI_PREFERENCES = {
    "primary_priority": "PRODUCTION_CONTINUITY",
    "secondary_priorities": [],
    "recommendation_style": "BALANCED",
    "risk_tolerance": "BALANCED",
}

INDUSTRY_OPTIONS = [
    "CNC / Mechanical",
    "Automotive Components",
    "Sheet Metal / Fabrication",
    "Electronics Assembly",
    "Plastics / Injection Molding",
    "Food & Beverage",
    "Textiles / Apparel",
    "Pharmaceutical",
    "Packaging",
    "Other",
]


def default_onboarding(name: str = "") -> Dict[str, Any]:
    return {
        "version": 1,
        "current_step": 1,
        "status": STATUS_DRAFT,
        "sections": {k: {"status": SECTION_PENDING, "data": {}} for k in STEP_KEYS},
    }


def normalize_onboarding(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a well-formed onboarding state, filling any missing pieces."""
    state = raw if isinstance(raw, dict) else {}
    out = default_onboarding()
    out["version"] = 1
    out["current_step"] = int(state.get("current_step") or 1)
    if state.get("status") in (STATUS_DRAFT, STATUS_IN_PROGRESS, STATUS_COMPLETE):
        out["status"] = state["status"]
    sections = state.get("sections") if isinstance(state.get("sections"), dict) else {}
    for k in STEP_KEYS:
        s = sections.get(k)
        if isinstance(s, dict):
            out["sections"][k] = {
                "status": s.get("status") or SECTION_PENDING,
                "data": s.get("data") if isinstance(s.get("data"), dict) else {},
            }
    return out


def section_complete(state: Dict[str, Any], key: str) -> bool:
    sec = (state.get("sections") or {}).get(key) or {}
    return sec.get("status") in (SECTION_AVAILABLE, SECTION_NOT_AVAILABLE, SECTION_DEFAULT)


def is_complete(state: Dict[str, Any]) -> bool:
    if state.get("status") == STATUS_COMPLETE:
        return True
    return all(section_complete(state, k) for k in REQUIRED_SECTIONS)


def factory_setup_complete(row: FactoryProfile) -> bool:
    """A factory is 'ready' when the profile is approved/completed."""
    status = (row.status or "").upper()
    if status in ("APPROVED", "COMPLETE"):
        return True
    state = normalize_onboarding(row.onboarding)
    return is_complete(state)


# ---------------------------------------------------------------------------
# CSV parsing (server-side safety net; the UI also previews client-side)
# ---------------------------------------------------------------------------
def parse_csv(text: str) -> List[Dict[str, str]]:
    if not text or not text.strip():
        return []
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    rows = []
    for raw in reader:
        rows.append({(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()})
    return rows


def _to_int(v, default=0):
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return default


def _to_float(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _parse_dt(v) -> Optional[datetime]:
    if v in (None, ""):
        return None
    s = str(v).strip().replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d", "%Y-%m-%d %H:%M", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            if fmt is None:
                dt = datetime.fromisoformat(s)
            else:
                dt = datetime.strptime(s, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def normalize_machine_code(value: str) -> Optional[str]:
    """M-001 / M001 / m-001 / M-01 all resolve to the canonical M-001 form."""
    if not value:
        return None
    import re

    t = str(value).strip().lower().replace(" ", "")
    m = re.fullmatch(r"m-?(\d{1,4})", t)
    if m:
        return f"M-{m.group(1).zfill(3)}"
    return None


# ---------------------------------------------------------------------------
# Section validators. Each returns (cleaned_data, errors, resolved_status).
# resolved_status is SECTION_AVAILABLE / SECTION_NOT_AVAILABLE / SECTION_DEFAULT.
# ---------------------------------------------------------------------------
def validate_company(data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    data = data or {}
    errors: List[str] = []
    name = str(data.get("name") or "").strip()
    industry = str(data.get("industry") or "").strip()
    products = data.get("products")
    if isinstance(products, list):
        products_clean = [str(p).strip() for p in products if str(p).strip()]
    else:
        products_clean = [p.strip() for p in str(products or "").split(",") if p.strip()]
    if not name:
        errors.append("Company / factory name is required.")
    if not industry:
        errors.append("Industry is required.")
    if not products_clean:
        errors.append("At least one product is required.")
    employee_count = data.get("employee_count")
    if employee_count not in (None, ""):
        try:
            employee_count = int(employee_count)
            if employee_count < 0:
                errors.append("Employee count must be zero or more.")
        except (TypeError, ValueError):
            errors.append("Employee count must be a number.")
            employee_count = None
    else:
        employee_count = None
    cleaned = {
        "name": name,
        "industry": industry,
        "products": products_clean,
        "employee_count": employee_count,
    }
    return cleaned, errors


def validate_production(data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    data = data or {}
    errors: List[str] = []
    processes_in = data.get("processes") or []
    processes = []
    seen_seq = set()
    seen_names = set()
    for p in processes_in:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or "").strip()
        if not name:
            errors.append("Production process name cannot be blank.")
            continue
        key = name.lower()
        if key in seen_names:
            errors.append(f"Duplicate production process '{name}'.")
            continue
        try:
            seq = int(p.get("sequence")) if p.get("sequence") not in (None, "") else len(processes) + 1
        except (TypeError, ValueError):
            errors.append(f"Invalid sequence for process '{name}'.")
            continue
        if seq < 1:
            errors.append(f"Sequence for '{name}' must be 1 or more.")
            continue
        if seq in seen_seq:
            errors.append(f"Duplicate sequence {seq}.")
            continue
        seen_seq.add(seq)
        seen_names.add(key)
        processes.append({"name": name, "sequence": seq, "description": str(p.get("description") or "").strip()})
    shifts = []
    for s in data.get("shifts") or []:
        if not isinstance(s, dict):
            continue
        name = str(s.get("name") or "").strip() or "Shift"
        start = str(s.get("start_time") or "").strip()
        end = str(s.get("end_time") or "").strip()
        import re

        ok_time = lambda t: bool(re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t))
        if not ok_time(start) or not ok_time(end):
            errors.append(f"Shift '{name}': start/end must be valid 24-hour times (HH:MM).")
            continue
        if start == end:
            errors.append(f"Shift '{name}': start and end cannot be identical.")
            continue
        try:
            brk = int(s.get("break_minutes") or 0)
        except (TypeError, ValueError):
            errors.append(f"Shift '{name}': break minutes must be a number.")
            continue
        if brk < 0 or brk > 720:
            errors.append(f"Shift '{name}': break minutes out of range.")
            continue
        wd = s.get("working_days")
        if isinstance(wd, str):
            wd = [d.strip() for d in wd.split(",") if d.strip()]
        shifts.append({
            "name": name, "start_time": start, "end_time": end,
            "break_minutes": brk, "working_days": wd if isinstance(wd, list) else [],
        })
    cap_in = data.get("capacity") or {}
    capacity = {}
    if isinstance(cap_in, dict) and cap_in.get("value") not in (None, ""):
        val = _to_float(cap_in.get("value"))
        if val is None or val <= 0:
            errors.append("Production capacity must be a positive number.")
        else:
            capacity = {"value": val, "unit": str(cap_in.get("unit") or "units/day").strip()}
    cleaned = {"processes": processes, "shifts": shifts, "capacity": capacity}
    return cleaned, errors


def validate_ai_preferences(data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    data = data or {}
    errors: List[str] = []

    def norm_enum(value, allowed):
        v = str(value or "").strip().upper()
        return v if v in allowed else None

    primary = norm_enum(data.get("primary_priority"), PRIMARY_PRIORITIES) or DEFAULT_AI_PREFERENCES["primary_priority"]
    if data.get("primary_priority") and norm_enum(data.get("primary_priority"), PRIMARY_PRIORITIES) is None:
        errors.append("Invalid primary priority.")
    style = norm_enum(data.get("recommendation_style"), RECOMMENDATION_STYLES) or DEFAULT_AI_PREFERENCES["recommendation_style"]
    risk = norm_enum(data.get("risk_tolerance"), RISK_TOLERANCES) or DEFAULT_AI_PREFERENCES["risk_tolerance"]
    secondary = []
    for s in data.get("secondary_priorities") or []:
        v = norm_enum(s, PRIMARY_PRIORITIES)
        if v is None:
            errors.append(f"Invalid secondary priority '{s}'.")
            continue
        if v == primary:
            errors.append("Primary priority cannot also be a secondary priority.")
            continue
        if v in secondary:
            errors.append(f"Duplicate secondary priority '{v}'.")
            continue
        secondary.append(v)
    return {
        "primary_priority": primary,
        "secondary_priorities": secondary,
        "recommendation_style": style,
        "risk_tolerance": risk,
    }, errors


def validate_thresholds(data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    data = data or {}
    errors: List[str] = []
    mode = "default" if data.get("mode") != "configured" else "configured"

    def clean_set(src, label):
        out = dict(DEFAULT_THRESHOLDS)
        for key in ("temp_max", "vibration_max", "current_max", "rpm_min"):
            if src and src.get(key) not in (None, ""):
                val = _to_float(src.get(key))
                if val is None or val <= 0:
                    errors.append(f"{label}: {key} must be a positive number.")
                else:
                    out[key] = val
        return out

    default = clean_set(data.get("default"), "Default thresholds")
    by_type = {}
    for mtype, src in (data.get("by_type") or {}).items():
        if not isinstance(src, dict):
            continue
        by_type[str(mtype)] = clean_set(src, f"{mtype} thresholds")
    return {"mode": mode, "default": default, "by_type": by_type}, errors


# Rows-based validators ------------------------------------------------------
def validate_employee_rows(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    cleaned, errors = [], []
    seen = set()
    for i, r in enumerate(rows or [], start=1):
        r = r or {}
        name = str(r.get("name") or "").strip()
        role = str(r.get("role") or "").strip()
        row_errs = []
        if not name:
            row_errs.append("name is required")
        if not role:
            row_errs.append("role is required")
        key = (name.lower(), role.lower())
        if name and key in seen:
            row_errs.append("duplicate row")
        if row_errs:
            errors.append({"row": i, "employee_id": r.get("employee_id"), "errors": row_errs})
            continue
        seen.add(key)
        skills = r.get("skills")
        if isinstance(skills, str):
            skills = [s.strip() for s in skills.split(",") if s.strip()]
        certs = r.get("certifications")
        if isinstance(certs, str):
            certs = [c.strip() for c in certs.split(",") if c.strip()]
        cleaned.append({
            "employee_id": str(r.get("employee_id") or "").strip() or None,
            "name": name,
            "role": role,
            "department": str(r.get("department") or "").strip() or None,
            "skills": skills or None,
            "certifications": certs or None,
            "shift": str(r.get("shift") or "").strip() or None,
            "experience_years": _to_int(r.get("experience_years"), 0) if r.get("experience_years") not in (None, "") else None,
        })
    return cleaned, errors


def validate_machine_rows(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    cleaned, errors = [], []
    seen = set()
    for i, r in enumerate(rows or [], start=1):
        r = r or {}
        raw_id = str(r.get("machine_id") or r.get("machine_code") or "").strip()
        name = str(r.get("machine_name") or r.get("name") or "").strip()
        code = normalize_machine_code(raw_id)
        row_errs = []
        if not raw_id:
            row_errs.append("machine_id is required")
        if not name:
            row_errs.append("machine_name is required")
        key = code or raw_id.lower()
        if code and key in seen:
            row_errs.append("duplicate machine")
        if row_errs:
            errors.append({"row": i, "machine_id": raw_id or None, "errors": row_errs})
            continue
        seen.add(key)
        # Keep the existing name convention "M-001 <name>" so machine-code
        # resolution and the factory map keep working unchanged.
        display_name = name
        if code and not name.lower().startswith(code.lower()):
            display_name = f"{code} {name}"
        cleaned.append({
            "machine_code": code or raw_id or None,
            "name": display_name,
            "machine_type": str(r.get("type") or r.get("machine_type") or "CNC").strip(),
            "location": str(r.get("location") or "").strip() or None,
            "department": str(r.get("department") or "").strip() or None,
            "criticality": str(r.get("criticality") or "").strip().upper() or None,
            "status": (str(r.get("status") or "OPERATIONAL").strip().upper() or "OPERATIONAL"),
        })
    return cleaned, errors


def validate_order_rows(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    cleaned, errors = [], []
    seen = set()
    for i, r in enumerate(rows or [], start=1):
        r = r or {}
        number = str(r.get("order_id") or r.get("order_number") or "").strip()
        row_errs = []
        if not number:
            row_errs.append("order_id is required")
        if number.lower() in seen:
            row_errs.append("duplicate order")
        if row_errs:
            errors.append({"row": i, "order_id": number or None, "errors": row_errs})
            continue
        seen.add(number.lower())
        dt = _parse_dt(r.get("deadline"))
        cleaned.append({
            "order_number": number,
            "customer_name": str(r.get("customer") or r.get("customer_name") or "").strip() or None,
            "product": str(r.get("product") or "").strip() or None,
            "quantity": _to_int(r.get("quantity"), 0),
            "priority": (str(r.get("priority") or "NORMAL").strip().upper() or "NORMAL"),
            # JSON-safe for onboarding storage; parsed back on insert.
            "deadline": dt.isoformat() if dt else None,
        })
    return cleaned, errors


MAINT_STATUSES = {"PENDING", "IN_PROGRESS", "COMPLETED", "DONE", "CANCELLED"}


def validate_maintenance_rows(rows: List[Dict[str, Any]], machines_by_code: Dict[str, Machine]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    cleaned, errors = [], []
    seen = set()
    for i, r in enumerate(rows or [], start=1):
        r = r or {}
        raw_machine = str(r.get("machine_id") or "").strip()
        code = normalize_machine_code(raw_machine)
        issue = str(r.get("issue") or "").strip()
        status = (str(r.get("status") or "COMPLETED").strip().upper() or "COMPLETED")
        dt = _parse_dt(r.get("date") or r.get("maintenance_date"))
        row_errs = []
        machine = machines_by_code.get(code) if code else None
        if not raw_machine:
            row_errs.append("machine_id is required")
        elif machine is None:
            row_errs.append(f"machine '{raw_machine}' not found")
        if not issue:
            row_errs.append("issue is required")
        if dt is None:
            row_errs.append("date is invalid")
        elif dt > datetime.now(timezone.utc):
            row_errs.append("date cannot be in the future")
        if status not in MAINT_STATUSES:
            row_errs.append(f"status '{status}' is not valid")
        key = (str(machine.id) if machine else raw_machine.lower(), issue.lower(), (dt.date().isoformat() if dt else ""))
        if key in seen:
            row_errs.append("duplicate maintenance record")
        if row_errs:
            errors.append({"row": i, "machine_id": raw_machine or None, "errors": row_errs})
            continue
        seen.add(key)
        cleaned.append({
            "machine_id": str(machine.id),  # JSON-safe; converted back on insert
            "issue": issue,
            "description": str(r.get("action") or r.get("description") or "").strip() or None,
            "technician": str(r.get("technician") or "").strip() or None,
            "maintenance_date": dt.isoformat() if dt else None,  # JSON-safe
            "resolution": str(r.get("resolution") or "").strip() or None,
            "status": status,
            "downtime_hours": r.get("downtime_hours"),
        })
    return cleaned, errors


# ---------------------------------------------------------------------------
# Factory registry helpers
# ---------------------------------------------------------------------------
def ensure_default_factory(db: Session) -> FactoryProfile:
    """Guarantee at least one (default/legacy) company exists."""
    existing = db.query(FactoryProfile).filter(FactoryProfile.is_default == True).first()  # noqa: E712
    if existing:
        return existing
    any_row = db.query(FactoryProfile).order_by(FactoryProfile.created_at.asc()).first()
    if any_row is not None:
        any_row.is_default = True
        any_row.name = any_row.name or any_row.industry or "IndAI Factory"
        db.commit()
        db.refresh(any_row)
        return any_row
    row = FactoryProfile(
        name="IndAI Demo Factory",
        industry="CNC / Mechanical",
        status="DRAFT",
        answers={},
        profile={},
        onboarding=default_onboarding("IndAI Demo Factory"),
        is_default=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def factory_counts(db: Session, factory_id: UUID, include_null: bool) -> Dict[str, int]:
    """Explicitly filtered counts so the selector can show real numbers."""
    def count(model):
        q = db.query(model)
        if include_null:
            q = q.filter((model.factory_id == factory_id) | (model.factory_id.is_(None)))
        else:
            q = q.filter(model.factory_id == factory_id)
        try:
            return q.count()
        except Exception:
            return 0

    return {
        "employees": count(Employee),
        "machines": count(Machine),
        "orders": count(Order),
        "maintenance": count(Maintenance),
    }


def factory_summary(db: Session, row: FactoryProfile) -> Dict[str, Any]:
    state = normalize_onboarding(row.onboarding)
    counts = factory_counts(db, row.id, bool(row.is_default))
    return {
        "id": str(row.id),
        "name": row.name or row.industry or "Unnamed Factory",
        "industry": row.industry,
        "status": row.status,
        "is_default": bool(row.is_default),
        "setup_complete": factory_setup_complete(row),
        "onboarding_status": state.get("status"),
        "current_step": state.get("current_step", 1),
        "counts": counts,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def profile_thresholds_from_onboarding(state: Dict[str, Any]) -> Dict[str, Any]:
    """Shape the stored thresholds for the existing threshold resolver."""
    data = ((state.get("sections") or {}).get("thresholds") or {}).get("data") or {}
    by_type = dict(data.get("by_type") or {})
    default = data.get("default") if isinstance(data.get("default"), dict) else DEFAULT_THRESHOLDS
    by_type["_default"] = {
        "temp_max": default.get("temp_max", DEFAULT_THRESHOLDS["temp_max"]),
        "vibration_max": default.get("vibration_max", DEFAULT_THRESHOLDS["vibration_max"]),
        "current_max": default.get("current_max", DEFAULT_THRESHOLDS["current_max"]),
        "rpm_min": default.get("rpm_min", DEFAULT_THRESHOLDS["rpm_min"]),
    }
    return by_type
