"""Deterministic + AI-assisted import logic (Phase C).

- Parse .csv / .xlsx (max 5 MB, max 20k rows).
- Propose source_column -> target_field mapping (LLM first, rule-based fallback).
- Commit: coerce types, validate with existing Pydantic Create schemas,
  resolve machine refs by code/name, bulk insert, skip duplicates/invalid.
- Telemetry imports NEVER auto-create incidents (historical rows).
"""
import csv
import io
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from openpyxl import load_workbook
from pydantic import BaseModel, ValidationError

from backend.schemas.employee import EmployeeCreate
from backend.schemas.machine import MachineCreate
from backend.schemas.order import OrderCreate
from backend.schemas.telemetry import TelemetryCreate

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 20_000

TARGETS = ("telemetry", "machines", "employees", "orders")

# Whitelist: exactly the existing Create-schema fields (+ machine_code alias for telemetry).
TARGET_FIELDS: Dict[str, List[str]] = {
    "telemetry": ["machine_code", "machine_id", "temperature", "vibration", "current", "rpm", "machine_status", "timestamp"],
    "machines": ["name", "machine_type", "location", "status", "health_status"],
    "employees": ["name", "role", "skills", "certifications", "shift", "status", "availability"],
    "orders": ["order_number", "customer_name", "product", "quantity", "priority", "status", "deadline", "progress"],
}

# Messy-header aliases for the deterministic fallback (Temp, Temp(C), Amp, Speed, Mach No, ...).
ALIASES: Dict[str, Dict[str, List[str]]] = {
    "telemetry": {
        "machine_code": ["mach no", "mach_no", "machine no", "machine code", "machinecode", "machine", "machine name", "machinename", "machine_id", "equipment", "asset"],
        "temperature": ["temp", "temp(c)", "temp_c", "temperature", "temperature_c", "heat", "degc"],
        "vibration": ["vib", "vibration", "vibe", "vib(mm/s)", "vibration_mm_s"],
        "current": ["amp", "amps", "current", "current_a", "amperage", "i(a)"],
        "rpm": ["speed", "rpm", "rev", "rotation", "rot speed"],
        "machine_status": ["status", "machine_status", "state", "run state", "run_state"],
        "timestamp": ["time", "timestamp", "date", "datetime", "recorded_at", "ts"],
    },
    "machines": {
        "name": ["name", "machine", "machine name", "equipment", "asset", "code"],
        "machine_type": ["type", "machine_type", "machine type", "category", "kind"],
        "location": ["location", "bay", "area", "site", "loc"],
        "status": ["status", "state"],
        "health_status": ["health", "health_status", "health status", "condition"],
    },
    "employees": {
        "name": ["name", "employee", "employee name", "full name", "worker"],
        "role": ["role", "job", "title", "position", "job title"],
        "skills": ["skills", "skill", "competencies"],
        "certifications": ["certifications", "certs", "certificates", "cert"],
        "shift": ["shift", "shifts"],
        "status": ["status", "emp status"],
        "availability": ["availability", "available", "avail"],
    },
    "orders": {
        "order_number": ["order_number", "order no", "orderno", "order #", "order id", "order_number ", "po", "order"],
        "customer_name": ["customer", "customer_name", "customer name", "client", "client name"],
        "product": ["product", "item", "part", "product name", "description"],
        "quantity": ["qty", "quantity", "amount", "count", "units"],
        "priority": ["priority", "prio", "urgency"],
        "status": ["status", "order status", "state"],
        "deadline": ["deadline", "due", "due date", "due_date", "delivery", "eta"],
        "progress": ["progress", "pct", "percent", "%", "completion"],
    },
}


class MappingProposal(BaseModel):
    mapping: Dict[str, Optional[str]]
    confidence: Dict[str, float]


def _norm(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (h or "").strip().lower()).strip()


def parse_file(filename: str, content: bytes) -> Tuple[List[str], List[Dict[str, Any]]]:
    if len(content) > MAX_BYTES:
        raise ValueError(f"File too large ({len(content)} bytes). Max is 5 MB.")
    lower = (filename or "").lower()
    if lower.endswith(".csv"):
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise ValueError("CSV has no header row.")
        headers = [h for h in reader.fieldnames if h is not None]
        rows = []
        for r in reader:
            rows.append({h: (v if v != "" else None) for h, v in r.items() if h is not None})
            if len(rows) > MAX_ROWS:
                raise ValueError("File exceeds 20,000 rows.")
        return headers, rows
    if lower.endswith((".xlsx", ".xlsm")):
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        try:
            header_row = next(it)
        except StopIteration:
            raise ValueError("Excel sheet is empty.")
        headers = [str(h).strip() if h is not None else f"col_{i}" for i, h in enumerate(header_row)]
        rows = []
        for rec in it:
            d: Dict[str, Any] = {}
            for h, v in zip(headers, rec):
                d[h] = None if v == "" else v
            # skip fully-empty rows
            if all(v is None for v in d.values()):
                continue
            rows.append(d)
            if len(rows) > MAX_ROWS:
                raise ValueError("File exceeds 20,000 rows.")
        return headers, rows
    raise ValueError("Unsupported file type. Use .csv or .xlsx.")


def rule_based_mapping(target: str, headers: List[str]) -> Tuple[Dict[str, Optional[str]], Dict[str, float]]:
    aliases = ALIASES.get(target, {})
    norm_headers = {h: _norm(h) for h in headers}
    mapping: Dict[str, Optional[str]] = {}
    confidence: Dict[str, float] = {}
    used_targets = set()
    for h in headers:
        nh = norm_headers[h]
        best: Optional[str] = None
        best_conf = 0.0
        for field, keys in aliases.items():
            if field in used_targets:
                continue
            for k in keys:
                nk = _norm(k)
                if nh == nk:
                    best, best_conf = field, 1.0
                    break
                if nk and nk in nh:
                    if 0.7 > best_conf:
                        best, best_conf = field, 0.7
            if best_conf == 1.0:
                break
        # exact target-field name match always wins
        if nh in [f for f in TARGET_FIELDS.get(target, [])]:
            best, best_conf = nh, 1.0
        mapping[h] = best
        confidence[h] = best_conf
        if best:
            used_targets.add(best)
    return mapping, confidence


def llm_mapping(target: str, headers: List[str], samples: List[Dict[str, Any]]) -> Optional[Tuple[Dict[str, Optional[str]], Dict[str, float]]]:
    """Ask the LLM for a mapping; return None when unavailable/invalid."""
    try:
        from backend.services.llm import LLMUnavailable, complete_json  # lazy: keeps import light
    except Exception:
        return None
    try:
        result = complete_json(
            "You map spreadsheet columns to database fields. Output JSON {mapping: {source_column: target_field|null}, confidence: {source_column: 0..1}}. "
            f"Allowed target fields for '{target}': {TARGET_FIELDS[target]}. Use null when no field fits. JSON ONLY.",
            {"target": target, "headers": headers, "sample_rows": samples[:5]},
            MappingProposal,
        )
        mapping = {h: result.mapping.get(h) for h in headers}
        # Validate: drop unknown fields.
        allowed = set(TARGET_FIELDS[target])
        for h, f in list(mapping.items()):
            if f is not None and f not in allowed:
                mapping[h] = None
        conf = {h: float(result.confidence.get(h, 0.5)) for h in headers}
        return mapping, conf
    except Exception:
        return None


def propose_mapping(target: str, headers: List[str], samples: List[Dict[str, Any]]) -> Tuple[Dict[str, Optional[str]], Dict[str, float], str]:
    llm = llm_mapping(target, headers, samples)
    if llm is not None:
        return llm[0], llm[1], "ai"
    m, c = rule_based_mapping(target, headers)
    return m, c, "rule-based"


def _coerce_number(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _coerce_int(v: Any) -> Optional[int]:
    n = _coerce_number(v)
    return None if n is None else int(n)


def _coerce_datetime(v: Any) -> Optional[datetime]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v
    s = str(v).strip()
    # Excel serial dates sometimes arrive as numbers via openpyxl data_only=False; read_only gives datetime already.
    try:
        # fromisoformat handles "2026-05-01", "2026-05-01T10:00:00", with space separator too.
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _coerce_json_dict(v: Any) -> Optional[Dict[str, Any]]:
    if v is None or v == "":
        return None
    if isinstance(v, dict):
        return v
    if isinstance(v, list):
        return {"items": v}
    s = str(v).strip()
    try:
        parsed = json.loads(s)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return {"items": parsed}
        return {"value": parsed}
    except (json.JSONDecodeError, ValueError):
        pass
    # comma-separated skills string -> {"items": [...]}
    parts = [p.strip() for p in re.split(r"[;,|]", s) if p.strip()]
    if len(parts) > 1:
        return {"items": parts}
    return {"value": s} if s else None


def build_validated_row(target: str, mapped: Dict[str, Any]) -> Tuple[Optional[BaseModel], Optional[str]]:
    """Coerce + validate one mapped row. Returns (obj, error)."""
    try:
        if target == "telemetry":
            data: Dict[str, Any] = {}
            if mapped.get("machine_id"):
                try:
                    data["machine_id"] = UUID(str(mapped["machine_id"]))
                except ValueError:
                    return None, f"bad machine_id '{mapped['machine_id']}'"
            for f in ("temperature", "vibration", "current", "rpm"):
                if mapped.get(f) is not None:
                    n = _coerce_number(mapped[f])
                    if mapped[f] not in (None, "") and n is None:
                        return None, f"bad number for {f}: '{mapped[f]}'"
                    data[f] = n
            if mapped.get("machine_status") is not None:
                data["machine_status"] = str(mapped["machine_status"]).strip().upper() or None
            if mapped.get("timestamp") is not None:
                dt = _coerce_datetime(mapped["timestamp"])
                if mapped["timestamp"] not in (None, "") and dt is None:
                    return None, f"bad timestamp: '{mapped['timestamp']}'"
                data["timestamp"] = dt
            obj = TelemetryCreate(**data)
            return obj, None
        if target == "machines":
            obj = MachineCreate(
                name=str(mapped.get("name") or "").strip(),
                machine_type=(str(mapped.get("machine_type")).strip() if mapped.get("machine_type") else None),
                location=(str(mapped.get("location")).strip() if mapped.get("location") else None),
                status=(str(mapped.get("status")).strip().upper() if mapped.get("status") else "OPERATIONAL"),
                health_status=(str(mapped.get("health_status")).strip().upper() if mapped.get("health_status") else "GOOD"),
            )
            return obj, None
        if target == "employees":
            obj = EmployeeCreate(
                name=str(mapped.get("name") or "").strip(),
                role=str(mapped.get("role") or "").strip(),
                skills=_coerce_json_dict(mapped.get("skills")),
                certifications=_coerce_json_dict(mapped.get("certifications")),
                shift=(str(mapped.get("shift")).strip() if mapped.get("shift") else None),
                status=(str(mapped.get("status")).strip().upper() if mapped.get("status") else "ACTIVE"),
                availability=(str(mapped.get("availability")).strip().upper() if mapped.get("availability") else "AVAILABLE"),
            )
            return obj, None
        if target == "orders":
            qty = _coerce_int(mapped.get("quantity")) if mapped.get("quantity") not in (None, "") else 0
            prog = _coerce_number(mapped.get("progress")) if mapped.get("progress") not in (None, "") else 0.0
            dl = _coerce_datetime(mapped.get("deadline")) if mapped.get("deadline") not in (None, "") else None
            if mapped.get("deadline") not in (None, "") and dl is None:
                return None, f"bad deadline: '{mapped['deadline']}'"
            obj = OrderCreate(
                order_number=str(mapped.get("order_number") or "").strip(),
                customer_name=(str(mapped.get("customer_name")).strip() if mapped.get("customer_name") else None),
                product=(str(mapped.get("product")).strip() if mapped.get("product") else None),
                quantity=qty or 0,
                priority=(str(mapped.get("priority")).strip().upper() if mapped.get("priority") else "NORMAL"),
                status=(str(mapped.get("status")).strip().upper() if mapped.get("status") else "PENDING"),
                deadline=dl,
                progress=prog or 0.0,
            )
            return obj, None
    except ValidationError as e:
        return None, str(e.errors()[0].get("msg", e)) if e.errors() else str(e)
    except Exception as e:
        return None, str(e)
    return None, f"unknown target '{target}'"
