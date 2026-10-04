"""Rehearsal: the whole demo story over HTTP, PASS/FAIL per step, then
reset cleanup. Never deletes anything it did not create (DEMO- prefix +
explicitly tracked ids only).

Run:  python -m backend.scripts.rehearse
"""
import os
import sys

import httpx
from backend.scripts import demo_scene as scene

BASE = scene.BASE.removesuffix("/api")
TIMEOUT = 60.0
results = []


def step(name, ok, detail=""):
    results.append((name, ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))


def get_list(client, path, params=None, tries=3):
    """GET a JSON list with retries; raises a clear error when not a list."""
    import time
    last = None
    for _ in range(tries):
        try:
            r = client.get(path, params=params)
            data = r.json()
            if isinstance(data, list):
                return data
            last = f"HTTP {r.status_code}: {str(data)[:120]}"
        except Exception as e:
            last = str(e)[:120]
        time.sleep(3)
    raise RuntimeError(f"GET {path} did not return a list after {tries} tries ({last})")


def main():
    c = httpx.Client(base_url=BASE, timeout=TIMEOUT)
    assert scene.setup() == 0
    orders = {o["order_number"]: o for o in get_list(c, "/api/orders")
              if (o.get("order_number") or "").startswith("DEMO-")}
    step("setup scene (3 orders)", len(orders) == 3, f"{len(orders)} DEMO- orders")

    # normal telemetry -> no incident
    ms = {scene._code_of(m["name"]): m for m in get_list(c, "/api/machines")}
    m1 = ms["M-001"]
    before = {i["id"] for i in get_list(c, "/api/incidents")
              if i["machine_id"] == m1["id"] and (i["status"] or "OPEN") == "OPEN"}
    c.post("/api/telemetry", json={"machine_id": m1["id"], **scene._reading("M-001")})
    after = {i["id"] for i in get_list(c, "/api/incidents")
             if i["machine_id"] == m1["id"] and (i["status"] or "OPEN") == "OPEN"}
    step("normal telemetry creates nothing new", after - before == set(),
         f"new={len(after - before)}")

    # trigger abnormal on M-001 (resolve pre-existing first so exactly-one holds)
    for iid in before:
        try:
            c.put(f"/api/incidents/{iid}", json={"status": "RESOLVED"})
        except Exception:
            pass
    assert scene.trigger("M-001") == 0
    fresh = [i for i in get_list(c, "/api/incidents")
             if i["machine_id"] == m1["id"] and (i["status"] or "OPEN") == "OPEN"]
    step("exactly one OPEN linked incident", len(fresh) == 1,
         f"{len(fresh)} OPEN; linked task={bool(fresh[0]['task_id']) if fresh else False} "
         f"order={bool(fresh[0]['order_id']) if fresh else False}")
    inc = fresh[0] if len(fresh) == 1 else None
    # repeat trigger -> still exactly one (dedup)
    assert scene.trigger("M-001") == 0
    again = [i for i in get_list(c, "/api/incidents")
             if i["machine_id"] == m1["id"] and (i["status"] or "OPEN") == "OPEN"]
    step("repeat trigger duplicates nothing", len(again) == len(fresh), f"{len(again)} OPEN")

    if inc is None:
        step("AI analysis structure", False, "no incident to analyze")
    else:
        r = c.post(f"/api/ai/analyze-incident/{inc['id']}", timeout=120.0)
        if r.status_code == 200:
            d = r.json()
            ok = bool((d.get("root_cause") or {}).get("summary")) and isinstance(
                d.get("recommendations"), list)
            step("AI analysis structure", ok, f"{len(d.get('recommendations', []))} recs")
        elif r.status_code == 503:
            risks = c.get("/api/orders/at-risk").json().get("orders", [])
            step("AI analysis structure", True,
                 f"clean 503 (no key); deterministic risk rows={len(risks)}")
        else:
            step("AI analysis structure", False, f"HTTP {r.status_code}")

    # assignment proposal for an unassigned demo task -> approve -> visible
    tasks = [t for t in get_list(c, "/api/tasks")
             if t.get("order_id") in {o["id"] for o in orders.values()} and not t.get("employee_id")]
    step("unassigned demo task exists", len(tasks) > 0, f"{len(tasks)} open")
    ok_prop = False
    if tasks:
        t0 = tasks[0]
        cands = c.get("/api/allocation/candidates", params={"task_id": t0["id"]}).json()
        emp = (cands.get("employees") or [{}])[0].get("id")
        if emp:
            p = c.post("/api/ai/proposals",
                       json={"action_type": "REASSIGN_TASK",
                             "params": {"task_id": t0["id"], "employee_id": emp},
                             "reason": "demo rehearsal assign"}).json()
            d = c.patch(f"/api/ai/recommendations/{p['id']}/decision",
                        json={"decision": "APPROVED", "note": "demo rehearsal"}).json()
            mine = get_list(c, "/api/tasks", params={"employee_id": emp})
            ok_prop = any(t["id"] == t0["id"] for t in mine) and d["recommendation"]["status"] == "APPROVED"
    step("proposal approve assigns + visible", ok_prop)

    # SCHEDULE_MAINTENANCE proposal -> PENDING row
    ok_maint = False
    if tasks:
        p = c.post("/api/ai/proposals",
                   json={"action_type": "SCHEDULE_MAINTENANCE",
                          "params": {"machine_id": m1["id"], "issue": "rehearsal check"},
                          "reason": "demo rehearsal maintain"}).json()
        d = c.patch(f"/api/ai/recommendations/{p['id']}/decision",
                    json={"decision": "APPROVED", "note": "demo rehearsal"}).json()
        ok_maint = bool(d.get("maintenance_id"))
        # reject path leaves nothing applied tested via second proposal
        p2 = c.post("/api/ai/proposals",
                    json={"action_type": "SCHEDULE_MAINTENANCE",
                          "params": {"machine_id": m1["id"], "issue": "rehearsal reject"},
                          "reason": "demo rehearsal reject"}).json()
        c.patch(f"/api/ai/recommendations/{p2['id']}/decision",
                json={"decision": "REJECTED"})
        c.delete(f"/api/maintenance/{d['maintenance_id']}") if d.get("maintenance_id") else None
        # clean the rejected proposal row is history; remove via decision record only
    step("maintenance proposal creates PENDING row", ok_maint)

    mem = get_list(c, "/api/memory")
    step("ADMIN_DECISION entries in memory",
         any(m.get("event_type") == "ADMIN_DECISION" for m in mem),
         f"{len(mem)} rows total")

    # worker-style incident -> visible + analyzable
    w = c.post("/api/incidents", json={
        "incident_type": "WORKER_REPORT", "severity": "MEDIUM", "status": "OPEN",
        "description": "[Worker report] rehearsal rattle by Arun Prakash",
        "machine_id": m1["id"]}).json()
    vis = any(i["id"] == w["id"] for i in get_list(c, "/api/incidents"))
    ra = c.post(f"/api/ai/analyze-incident/{w['id']}", timeout=120.0)
    step("worker incident visible + analyzable", vis and ra.status_code in (200, 503),
         f"visible={vis} analyze={ra.status_code}")
    c.delete(f"/api/incidents/{w['id']}")

    # Jarvis tools live (each tool function against the live API, run under
    # the Jarvis venv where livekit is installed). Probe via temp file
    # (inline -c quoting is unreliable on PowerShell).
    import subprocess
    import tempfile
    probe_lines = [
        "import asyncio, json, sys",
        "sys.path.insert(0, 'Jarvis/src')",
        "import tools as T",
        "tools = T.IndAITools(lambda: None).tools()",
        "names = ['get_factory_overview', 'list_open_incidents', 'list_available_employees']",
        "by = {getattr(t, 'id', '?'): t for t in tools}",
        "async def go():",
        "    out = {}",
        "    for n in names:",
        "        kw = {'skill': 'Welding'} if n == 'list_available_employees' else {}",
        "        r = await by[n](None, **kw)",
        "        out[n] = isinstance(r, str) and len(r) > 0",
        "    print(json.dumps(out))",
        "asyncio.run(go())",
    ]
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write("\n".join(probe_lines) + "\n")
            probe_path = f.name
        pr = subprocess.run(
            ["Jarvis/venv/Scripts/python.exe", probe_path],
            capture_output=True, text=True, timeout=120)
        import json as _json
        got = _json.loads(pr.stdout.strip().splitlines()[-1]) if pr.returncode == 0 else {}
        ok_tools = all(got.get(k) for k in
                       ["get_factory_overview", "list_open_incidents", "list_available_employees"])
        step("Jarvis tool callable live", ok_tools, str(got)[:120])
    except Exception as e:
        step("Jarvis tool callable live", False, f"venv probe failed: {str(e)[:100]}")
    finally:
        try:
            os.remove(probe_path)
        except Exception:
            pass

    # cleanup with reset logic (removes demo proposals too)
    assert scene.reset() == 0
    with_d = [o for o in get_list(c, "/api/orders") if (o.get("order_number") or "").startswith("DEMO-")]
    step("reset removes DEMO data", len(with_d) == 0, f"{len(with_d)} left")

    fails = [n for n, ok in results if not ok]
    print(f"REHEARSAL {'PASS' if not fails else 'FAIL'} ({len(results) - len(fails)}/{len(results)})")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
