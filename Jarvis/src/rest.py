"""IndAI REST client for the voice agent (no DB credentials, httpx only)."""
from __future__ import annotations

import os

import httpx

BASE = os.environ.get("INDAI_API_URL", "http://127.0.0.1:8000/api").rstrip("/")
# Backend tool-call bound: keeps every voice-tool REST call inside the turn
# watchdog budget (slow backend -> short spoken error, never silence).
TIMEOUT = 6.0


def _url(path: str) -> str:
    return f"{BASE}{path if path.startswith('/') else '/' + path}"


async def api_get(path: str, params: dict | None = None) -> tuple[int, object]:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.get(_url(path), params=params or {})
            try:
                return r.status_code, r.json()
            except ValueError:
                return r.status_code, r.text[:500]
    except Exception as e:
        return 0, f"API unreachable: {str(e)[:150]}"


async def api_post(path: str, body: dict | None = None) -> tuple[int, object]:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.post(_url(path), json=body or {})
            try:
                return r.status_code, r.json()
            except ValueError:
                return r.status_code, r.text[:500]
    except Exception as e:
        return 0, f"API unreachable: {str(e)[:150]}"


async def api_patch(path: str, body: dict | None = None) -> tuple[int, object]:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.patch(_url(path), json=body or {})
            try:
                return r.status_code, r.json()
            except ValueError:
                return r.status_code, r.text[:500]
    except Exception as e:
        return 0, f"API unreachable: {str(e)[:150]}"
