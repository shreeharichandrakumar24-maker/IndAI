"""Demo scene: setup | trigger | reset (TASK 2).

Talks to the running API over HTTP via httpx. Never touches the DB.
Run:  python -m backend.scripts.demo_scene setup|trigger|reset [--machine M-001]

- setup (idempotent): NORMAL telemetry per canonical machine; 3 DEMO- orders
  (comfortable / tight / at-risk), 2-3 tasks each on seeded workers by skill
  (some UNASSIGNED for allocation demos), IN_PROGRESS runs on M-001/M-003/M-006.
- trigger: posts the abnormal payload for one machine, prints the OPEN
  incident + links + deterministic risk (backup for the simulator button).
- reset: removes ONLY what the demo created (DEMO- orders cascade tasks/runs;
  demo-linked + demo-window incidents/maintenance; rejects demo PENDING
  proposals), posts NORMAL readings, and reports anything it keeps
  (ai_recommendations history rows stay rejected, telemetry history stays,
  memory stays as the story record).
"""
import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import httpx

BASE = os.environ.get("INDAI_API_URL", "http://127.0.0.1:8000/api").rstrip("/")
TIMEOUT = 30.0
STATE_FILE = os.path.join(tempfile.gettempdir(), "indai_demo_scene.json")

# code -> (machine_type, normal, abnormal); mirrors the IoT simulator config
FLEET = {
    "M-001": ("CNC", (68, 2.0, 8.0, 1450), (95, 6.5, 12.0, 1200)),
    "M-002": ("CNC", (72, 2.5, 9.5, 1200), (98, 7.0, 14.0, 900)),
    "M-003": ("Press", (55, 3.5, 15.0, 0), (80, 8.0, 22.0, 0)),
    "M-004": ("Grinder", (60, 4.0, 7.5, 3000), (88, 9.5, 11.0, 2200)),
    "M-005": ("Welder", (75, 1.2, 18.0, 0), (105, 4.5, 26.0, 0)),
    "M-006": ("Robot", (48, 1.8, 5.5, 900), (72, 5.5, 9.0, 600)),
    "M-007": ("Laser", (62, 1.0, 11.0, 0), (90, 3.8, 16.0, 0)),
    "M-008": ("Molder", (85, 2.8, 13.5, 750), (115, 7.5, 19.0, 500)),
}

# order_number, product, qty, priority, deadline offset days, progress, run(machine, target, completed)
ORDERS = [
    ("DEMO-1", "Demo brackets", 100, "NORMAL", 30, 0.7, ("M-001", 100, 80)),
    ("DEMO-2", "Demo shafts", 200, "HIGH", 2, 0.2, ("M-003", 100, 20)),
    ("DEMO-3", "Demo frames", 150, "URGENT", -1, 0.1, ("M-006", 100, 5)),
]

# (task name, skill, machine code or None, order index, assignee name or None)
TASKS = [
    ("Demo CNC milling", "CNC operation", "M-001", 0, "Arun Prakash"),
    ("Demo QC check", "Quality inspection", "M-001", 0, "Sanjay Patel"),
    ("Demo deburr batch", "Assembly", None, 0, None),
    ("Demo press forming", "Press operation", "M-003", 1, "Ravi Shankar"),
    ("Demo weld frames", "Welding", "M-005", 1, "Suresh Kumar"),
    ("Demo laser cut", "Laser operation", None, 1, None),
    ("Demo robot assembly", "Assembly", "M-006", 2, "Vikram Singh"),
    ("Demo preventive check", "Maintenance", "M-001", 2, "Deepak Joshi"),
    ("Demo molding run", "Molding", None, 2, None),
]


def _client():
    return httpx.Client(base_url=BASE, timeout=TIMEOUT)


def _code_of(name):
    import re
    m = re.match(r"^(M-\d{3})", (name or "").strip())
    return m.group(1) if m else None


def _reading(code, abnormal=False):
    _, normal, abn = FLEET[code]
    t, v, c, r = abn if abnormal else normal
    return {"temperature": t, "vibration": v, "current": c, "rpm": r,
            "machine_status": "RUNNING"}


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)


def setup():
    created = {"orders": [], "tasks": [], "runs": [], "telemetry": []}
    skipped = {"orders": [], "tasks": []}
    with _client() as c:
        machines = { _code_of(m["name"]): m for m in c.get("/machines").json() }
        missing = [code for code in FLEET if code not in machines]
        if missing:
            print(f"ABORT: canonical machines missing: {missing}")
            return 1
        for code, m in machines.items():
            if code not in FLEET:
                continue
            body = {"machine_id": m["id"], **_reading(code)}
            c.post("/telemetry", json=body)
            created["telemetry"].append(code)
        employees = {e["name"]: e for e in c.get("/employees").json()}
        orders = {o["order_number"]: o for o in c.get("/orders").json()}
        order_ids = {}
        for number, product, qty, prio, off, prog, run in ORDERS:
            if number in orders:
                skipped["orders"].append(number)
                order_ids[number] = orders[number]["id"]
                continue
            dl = (datetime.now(timezone.utc) + timedelta(days=off)).isoformat()
            o = c.post("/orders", json={"order_number": number, "customer_name": "Demo Customer",
                                        "product": product, "quantity": qty, "priority": prio,
                                        "status": "IN_PROGRESS", "deadline": dl,
                                        "progress": prog}).json()
            order_ids[number] = o["id"]
            created["orders"].append(number)
            mcode, target, done = run
            mid = machines[mcode]["id"]
            r = c.post("/production", json={"order_id": o["id"], "machine_id": mid,
                                            "status": "IN_PROGRESS", "quantity_target": target,
                                            "quantity_completed": done}).json()
            created["runs"].append(r["id"][:8])
        existing_tasks = {(t["name"], t.get("order_id")) for t in c.get("/tasks").json()}
        for name, skill, mcode, oi, worker in TASKS:
            number = ORDERS[oi][0]
            if (name, order_ids[number]) in existing_tasks:
                skipped["tasks"].append(name)
                continue
            payload = {"name": name, "required_skill": skill, "priority": "NORMAL",
                       "status": "PENDING", "order_id": order_ids[number], "progress": 0.0}
            if mcode:
                payload["machine_id"] = machines[mcode]["id"]
            if worker and worker in employees:
                payload["employee_id"] = employees[worker]["id"]
            t = c.post("/tasks", json=payload).json()
            created["tasks"].append(f"{name} -> {worker or 'UNASSIGNED'}")
        save_state({"orders": list(order_ids.values()),
                    "since": datetime.now(timezone.utc).isoformat()})
    print(f"setup: orders created {len(created['orders'])} skipped {len(skipped['orders'])}; "
          f"tasks created {len(created['tasks'])} skipped {len(skipped['tasks'])}; "
          f"runs {len(created['runs'])}; telemetry posted for {len(created['telemetry'])} machines")
    for t in created["tasks"]:
        print(f"  task: {t}")
    return 0


def trigger(machine_code="M-001"):
    if machine_code not in FLEET:
        print(f"Unknown machine {machine_code}; use one of {sorted(FLEET)}")
        return 1
    with _client() as c:
        machines = {_code_of(m["name"]): m for m in c.get("/machines").json()}
        m = machines[machine_code]
        body = {"machine_id": m["id"], **_reading(machine_code, abnormal=True)}
        c.post("/telemetry", json=body)
        # Re-read through the check endpoint so dedup is visible.
        chk = c.post(f"/telemetry/{m['id']}/check").json()
        if not chk.get("incident_id"):
            print("No OPEN incident found after abnormal post (detection may lag).")
            return 1
        inc = c.get(f"/incidents/{chk['incident_id']}").json()
        dup = " (already existed - simulator or earlier trigger)" if chk.get("already_existed") else ""
        print(f"incident: {inc['id']} severity={inc['severity']} type={inc['incident_type']}{dup}")
        print(f"linked: task={str(inc['task_id'])[:8] if inc['task_id'] else None} "
              f"order={str(inc['order_id'])[:8] if inc['order_id'] else None} "
              f"employee={str(inc['employee_id'])[:8] if inc['employee_id'] else None}")
        if inc["order_id"]:
            risks = c.get("/orders/at-risk").json().get("orders", [])
            hit = next((r for r in risks if r["order_id"] == inc["order_id"]), None)
            if hit:
                print(f"deterministic risk: {hit['risk_level']} - {hit['reason']}")
        st = load_state()
        st["incident_ids"] = sorted({*st.get("incident_ids", []), inc["id"]})
        save_state(st)
    return 0


def reset():
    st = load_state()
    removed = {"orders": 0, "tasks": 0, "runs": 0, "incidents": 0,
               "maintenance": 0, "proposals_rejected": 0}
    kept = []
    with _client() as c:
        since = st.get("since")
        demo_order_ids = set(st.get("orders", []))
        if not demo_order_ids:
            demo_order_ids = {o["id"] for o in c.get("/orders").json()
                              if (o.get("order_number") or "").startswith("DEMO-")}
        demo_task_ids = {t["id"] for t in c.get("/tasks").json() if t.get("order_id") in demo_order_ids}
        # incidents: demo-linked ones + OPEN ones created after setup on any machine
        for i in c.get("/incidents").json():
            linked = i.get("order_id") in demo_order_ids or i.get("task_id") in demo_task_ids
            in_window = False
            if since and (i.get("status") or "OPEN") == "OPEN":
                try:
                    in_window = i.get("created_at", "") >= since
                except TypeError:
                    in_window = False
            if linked or in_window:
                c.delete(f"/incidents/{i['id']}")
                removed["incidents"] += 1
        # maintenance referencing deleted incidents or demo machines in window
        for mnt in c.get("/maintenance").json():
            hit_incident = any(s in (mnt.get("issue") or "") for s in st.get("incident_ids", []))
            in_window = False
            if since:
                try:
                    in_window = (mnt.get("created_at", "") >= since)
                except TypeError:
                    in_window = False
            if hit_incident or in_window:
                c.delete(f"/maintenance/{mnt['id']}")
                removed["maintenance"] += 1
        # pending demo proposals -> reject (record-only, keeps history tidy)
        for p in c.get("/ai/proposals", params={"status": "PENDING"}).json():
            title = p.get("recommendation") or ""
            if "DEMO" in title.upper() or (p.get("reason") or "").startswith("demo"):
                c.patch(f"/ai/recommendations/{p['id']}/decision",
                        json={"decision": "REJECTED", "note": "demo reset"})
                removed["proposals_rejected"] += 1
        # orders last (cascades tasks + runs)
        for oid in demo_order_ids:
            try:
                tasks_before = [t["id"] for t in c.get("/tasks").json() if t.get("order_id") == oid]
                runs_before = [r["id"] for r in c.get("/production", params={"order_id": oid}).json()]
                c.delete(f"/orders/{oid}")
                removed["orders"] += 1
                removed["tasks"] += len(tasks_before)
                removed["runs"] += len(runs_before)
            except Exception:
                pass
        kept.append("ai_recommendations history rows stay (rejected, not pending)")
        kept.append("telemetry history rows stay (latest readings overwritten below)")
        kept.append("factory_memory rows stay (the demo story record)")
        # NORMAL readings so the map goes green
        machines = {_code_of(m["name"]): m for m in c.get("/machines").json()}
        for code, m in machines.items():
            if code in FLEET:
                c.post("/telemetry", json={"machine_id": m["id"], **_reading(code)})
    try:
        os.remove(STATE_FILE)
    except OSError:
        pass
    print(f"reset: orders {removed['orders']}, tasks {removed['tasks']}, runs {removed['runs']}, "
          f"incidents {removed['incidents']}, maintenance {removed['maintenance']}, "
          f"proposals rejected {removed['proposals_rejected']}")
    print("kept (by design): " + "; ".join(kept))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="demo_scene")
    ap.add_argument("command", choices=["setup", "trigger", "reset"])
    ap.add_argument("--machine", default="M-001")
    args = ap.parse_args(argv)
    if args.command == "setup":
        return setup()
    if args.command == "trigger":
        return trigger(args.machine)
    return reset()


if __name__ == "__main__":
    sys.exit(main())
