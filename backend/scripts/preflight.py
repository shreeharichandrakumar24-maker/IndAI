"""Preflight: is the demo stage ready? Prints PASS/FAIL/WARN per item,
exits non-zero on any FAIL, and ends with a READY / NOT READY verdict.

Run:  python -m backend.scripts.preflight
Only reads (plus one LLM ping that writes nothing).
"""
import os
import sys
from datetime import datetime, timezone

import httpx

BASE = os.environ.get("INDAI_API_URL", "http://127.0.0.1:8000").rstrip("/")
WEB = os.environ.get("INDAI_WEB_URL", "http://127.0.0.1:5173").rstrip("/")
SIM = os.environ.get("INDAI_SIM_URL", "http://localhost:5174").rstrip("/")
TIMEOUT = 15.0
FRESH_S = 60

results = []


def check(name, status, detail=""):
    results.append((name, status, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))


def main():
    try:
        c = httpx.Client(base_url=BASE, timeout=TIMEOUT)
    except Exception as e:
        print(f"[FAIL] client - {e}")
        return 1
    try:
        h = c.get("/api/health").json()
        check("backend /health", "PASS" if h.get("status") == "ok" else "FAIL", str(h))
    except Exception as e:
        check("backend /health", "FAIL", str(e)[:100])
        print("NOT READY"); return 1
    try:
        c.get("/api/health/db")
        check("backend /health/db", "PASS")
    except Exception as e:
        check("backend /health/db", "FAIL", str(e)[:100])

    try:
        machines = c.get("/api/machines").json()
        import re
        codes = sorted([m.group(1) for m in
                        [re.match(r"^(M-\d{3})", (m.get("name") or "")) for m in machines] if m])
        dupes = len(codes) != len(set(codes))
        ok = all(f"M-00{i}" in codes for i in range(1, 9)) and not dupes
        check("8 canonical machines, no duplicates", "PASS" if ok else "FAIL", f"{len(codes)} codes")
    except Exception as e:
        check("8 canonical machines, no duplicates", "FAIL", str(e)[:100])
        machines = []

    try:
        p = c.get("/api/profile").json()
        check("profile APPROVED", "PASS" if p.get("status") == "APPROVED" else "FAIL",
              str(p.get("status")))
    except Exception as e:
        check("profile APPROVED", "FAIL", str(e)[:100])

    try:
        emps = c.get("/api/employees").json()
        names = {e.get("name") for e in emps}
        from backend.scripts.seed_employees import DEMO
        want = {d[0] for d in DEMO}
        missing = want - names
        if not missing:
            check("15 seeded workers + credentials", "PASS", "15/15 present")
        else:
            check("15 seeded workers + credentials", "FAIL", f"missing: {sorted(missing)}")
        # Prove credentials work end-to-end with the first pair from the
        # gitignored creds file (values never printed). Skipped if absent.
        # Creds file is 6-column (name|role|code|email|username|password);
        # old 4-column (name|role|username|password) files still parse.
        try:
            import pathlib
            cred_file = pathlib.Path("docs/demo_worker_credentials.txt")
            pair = None
            fallback = None
            if cred_file.exists():
                for line in cred_file.read_text(encoding="utf-8").splitlines():
                    if "|" not in line:
                        continue
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 6:
                        uname, pwd = parts[4], parts[5]
                    elif len(parts) == 4:
                        uname, pwd = parts[2], parts[3]
                    else:
                        continue
                    if not uname or not pwd or "unchanged" in pwd.lower():
                        continue
                    if fallback is None:
                        fallback = (uname, pwd)
                    if "Worker@" in line:
                        pair = (uname, pwd)
                        break
            pair = pair or fallback
            if pair:
                r = c.post("/api/worker-auth/login",
                           json={"identifier": pair[0], "password": pair[1]})
                check("worker login round-trip", "PASS" if r.status_code == 200 else "FAIL",
                      f"HTTP {r.status_code}")
            else:
                check("worker login round-trip", "WARN", "creds file has no usable pair")
        except Exception as e:
            check("worker login round-trip", "FAIL", str(e)[:100])
    except Exception as e:
        check("15 seeded workers + credentials", "FAIL", str(e)[:100])

    try:
        now = datetime.now(timezone.utc)
        stale = []
        for m in machines:
            rows = c.get(f"/api/telemetry/{m['id']}", params={"limit": 1}).json()
            if not rows:
                stale.append((_code(m), "no data"))
                continue
            ts = rows[0].get("timestamp")
            try:
                age = (now - datetime.fromisoformat(str(ts).replace("Z", "+00:00"))).total_seconds()
            except (ValueError, TypeError):
                age = 1e9
            if age > FRESH_S:
                stale.append((_code(m), f"{int(age)}s old"))
        if not stale:
            check("telemetry fresh <60s on all 8", "PASS")
        else:
            check("telemetry fresh <60s on all 8", "WARN", f"{len(stale)} stale (simulator off?): {stale[:4]}")
    except Exception as e:
        check("telemetry fresh <60s on all 8", "FAIL", str(e)[:100])

    try:
        from backend.services.llm import complete_json, LLMUnavailable
        from pydantic import BaseModel
        class Ping(BaseModel):
            ok: bool
        try:
            complete_json("Reply with JSON only.", {"ping": True}, Ping)
            check("LLM ping (valid JSON)", "PASS")
        except LLMUnavailable as e:
            check("LLM ping (valid JSON)", "WARN", f"{str(e)[:100]} - deterministic fallbacks will be used")
    except Exception as e:
        check("LLM ping (valid JSON)", "WARN", str(e)[:100])

    for var, path in (("LIVEKIT_URL", "backend/.env"), ("LIVEKIT_API_KEY", "backend/.env"),
                      ("LIVEKIT_API_SECRET", "backend/.env")):
        present = _var_present(path, var)
        check(f"{var} name in {path}", "PASS" if present else "WARN",
              "" if present else "voice will 503")
    for var in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"):
        present = _var_present("Jarvis/.env.local", var)
        check(f"{var} name in Jarvis/.env.local", "PASS" if present else "WARN",
              "" if present else "agent cannot start")

    try:
        r = c.post("/api/voice/token")
        if r.status_code == 200:
            d = r.json()
            ok = bool(d.get("token") and d.get("url")) and "secret" not in str(d).lower().replace("api_secret", "")
            check("POST /api/voice/token 200, no secret", "PASS" if ok else "FAIL")
        elif r.status_code == 503:
            check("POST /api/voice/token 200, no secret", "WARN", "voice not configured (503 by design)")
        else:
            check("POST /api/voice/token 200, no secret", "FAIL", f"HTTP {r.status_code}")
    except Exception as e:
        check("POST /api/voice/token 200, no secret", "FAIL", str(e)[:100])

    for name, url in (("admin frontend 5173", WEB), ("simulator 5174", SIM)):
        try:
            r = httpx.get(url, timeout=10.0)
            check(name, "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code}")
        except Exception as e:
            check(name, "FAIL", str(e)[:100])

    try:
        leftovers = [o.get("order_number") for o in c.get("/api/orders").json()
                     if (o.get("order_number") or "").startswith("DEMO-")]
        if leftovers:
            check("no DEMO- leftovers", "WARN", f"{leftovers} - run demo_scene reset")
        else:
            check("no DEMO- leftovers", "PASS")
    except Exception as e:
        check("no DEMO- leftovers", "FAIL", str(e)[:100])

    # Non-demo OPEN incidents already red on the map confuse the story.
    try:
        demo_ids = set()
        try:
            demo_ids = {o["id"] for o in c.get("/api/orders").json()
                        if (o.get("order_number") or "").startswith("DEMO-")}
        except Exception:
            pass
        noisy = [i for i in c.get("/api/incidents").json()
                 if (i.get("status") or "OPEN") == "OPEN" and i.get("order_id") not in demo_ids]
        if noisy:
            check("no stray OPEN incidents", "WARN", f"{len(noisy)} pre-existing OPEN (map already red) - resolve them or accept the noise")
        else:
            check("no stray OPEN incidents", "PASS")
    except Exception as e:
        check("no stray OPEN incidents", "FAIL", str(e)[:100])

    fails = [n for n, s, _ in results if s == "FAIL"]
    print("READY" if not fails else "NOT READY")
    return 1 if fails else 0


def _code(m):
    import re
    mt = re.match(r"^(M-\d{3})", (m.get("name") or ""))
    return mt.group(1) if mt else "?"


def _var_present(path, var):
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s.startswith(var + "=") and len(s.split("=", 1)[1].strip().strip("'\"")) > 0:
                    return True
    except OSError:
        pass
    return False


if __name__ == "__main__":
    sys.exit(main())
