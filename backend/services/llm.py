"""Single gateway for all LLM JSON calls (Phase A).

All AI features must use ONLY `complete_json` from this file.
Deterministic code must be labeled deterministic; LLM output is labeled AI.
Never fake AI results: on missing key / network error / invalid JSON after
one retry, raise LLMUnavailable so callers can return a clear
"AI unavailable" state or a labeled deterministic fallback.
"""
from typing import Any, Dict, Type, TypeVar
import json

import httpx
from pydantic import BaseModel, ValidationError

from backend.core.config import settings

T = TypeVar("T", bound=BaseModel)


class LLMUnavailable(Exception):
    """Raised when the LLM cannot produce validated JSON (no key, HTTP error, bad JSON)."""
    pass


def _base_url() -> str:
    if settings.LLM_BASE_URL:
        return settings.LLM_BASE_URL.rstrip("/")
    # Only OpenAI-compatible endpoints are supported for now.
    return "https://api.openai.com/v1"


def is_configured() -> bool:
    return bool((settings.LLM_API_KEY or "").strip())


def complete_json(system_prompt: str, user_payload: Dict[str, Any], schema_model: Type[T],
                  model: str | None = None) -> T:
    """Call the LLM in JSON mode, parse + validate against schema_model.

    Some providers (e.g. Groq gpt-oss) reject response_format=json_object
    with HTTP 400: on a first-attempt 400 the request is retried once
    WITHOUT response_format (the prompts still demand JSON ONLY). Then one
    more retry on invalid JSON. Timeout ~30s. Raises LLMUnavailable after
    that.
    """
    if not is_configured():
        raise LLMUnavailable("LLM API key not configured (LLM_API_KEY is empty).")

    url = f"{_base_url()}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    # Ask the model to emit ONLY JSON matching the schema.
    schema_hint = ""
    try:
        schema_hint = json.dumps(schema_model.model_json_schema(), indent=1)[:4000]
    except Exception:
        schema_hint = schema_model.__name__
    body = {
        "model": model or settings.LLM_MODEL,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt + "\nRespond with JSON ONLY. No markdown, no commentary."},
            {
                "role": "user",
                "content": json.dumps({"payload": user_payload, "json_schema": schema_hint}, default=str),
            },
        ],
    }

    last_err: Exception | None = None
    json_mode = True
    for attempt in range(3):  # json-mode, plain retry, validation retry
        if not json_mode:
            body.pop("response_format", None)
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, headers=headers, json=body)
            if resp.status_code in (401, 403):
                raise LLMUnavailable(f"LLM auth failed (HTTP {resp.status_code}). Check LLM_API_KEY.")
            if resp.status_code == 429:
                raise LLMUnavailable("LLM rate-limited (HTTP 429). Try again later.")
            if resp.status_code == 400 and json_mode and attempt == 0:
                # Provider rejects JSON mode (e.g. Groq gpt-oss): retry plain.
                json_mode = False
                last_err = ValueError(f"JSON mode rejected (HTTP 400): {resp.text[:200]}")
                continue
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content) if isinstance(content, str) else content
            # Some models wrap in {"result": {...}} — unwrap one level if needed.
            if isinstance(parsed, dict) and schema_model.__name__.lower() not in [k.lower() for k in parsed.keys()]:
                pass  # keep as-is; validation decides
            return schema_model.model_validate(parsed)
        except LLMUnavailable:
            raise
        except (ValidationError, json.JSONDecodeError, KeyError, IndexError, httpx.HTTPError, ValueError) as e:
            last_err = e
            continue
    raise LLMUnavailable(f"LLM did not return valid JSON after retry: {last_err}")
