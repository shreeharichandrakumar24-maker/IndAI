"""Unit tests for Jarvis tools. Mocked by default; --live hits the real API.

Run:  venv python src/test_tools.py [--live]
"""
import asyncio
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else ".")


async def _mocked():
    import tools as T

    async def fake_get(path, params=None):
        if path == "/machines":
            return 200, [{"id": "m1", "name": "M-001 CNC Mill", "status": "OPERATIONAL",
                          "health_status": "GOOD"}]
        if path == "/employees":
            return 200, [{"id": "e1", "name": "Arun Prakash", "role": "CNC Operator",
                          "availability": "AVAILABLE", "shift": "Morning", "skills": {"items": ["CNC operation"]}}]
        if path == "/tasks":
            return 200, [{"id": "t1", "name": "Mill brackets", "status": "PENDING",
                          "required_skill": "CNC operation", "employee_id": None}]
        if path == "/incidents":
            return 200, []
        if path == "/ai/assistant/quick/overview":
            return 200, {"summary": "mock overview"}
        if path.startswith("/telemetry/"):
            return 200, [{"temperature": 68, "vibration": 2.0, "current": 8.0,
                          "rpm": 1450, "machine_status": "RUNNING"}]
        if path == "/allocation/candidates":
            return 200, {"employees": [{"id": "e1", "name": "Arun Prakash", "open_tasks": 0}]}
        if path == "/tasks/t1":
            return 200, {"id": "t1", "name": "Mill brackets", "status": "IN_PROGRESS",
                         "required_skill": "CNC operation", "employee_id": "e1",
                         "machine_id": "m1", "order_id": "o1", "progress": 0.5,
                         "deadline": "2026-10-20T00:00:00", "updated_at": "2026-10-04T10:42:00"}
        if path == "/employees/e1":
            return 200, {"id": "e1", "name": "Arun Prakash", "role": "CNC Operator"}
        if path == "/employees/e1/worker-login":
            return 200, {"has_login": True, "employee_code": "EMP-005", "email": None, "username": None}
        if path == "/production":
            return 200, [{"id": "r1", "task_id": "t1", "quantity_target": 100, "quantity_completed": 40}]
        if path == "/memory":
            return 200, [{"id": "m1", "title": "Arun Prakash started 'Mill brackets'",
                         "created_at": "2026-10-04T10:42:00"}]
        if path == "/plans":
            return 200, [{"id": "p1", "title": "Week 42 batch", "status": "APPROVED"}]
        if path == "/reports/weekly":
            return 200, {"orders": {"completed_this_week": 3, "late_now": 1, "active_total": 7},
                         "downtime": {"incidents_raised_this_week": 2, "currently_open": 1},
                         "decisions": {"admin_decisions_this_week": 4,
                                       "recommendations_approved": 1,
                                       "recommendations_rejected": 0},
                         "top_failing_machines": [{"name": "M-001 CNC Mill", "incidents": 2}]}
        if path == "/profile":
            return 200, {"industry": "CNC / Mechanical", "status": "APPROVED",
                         "profile": {"machines": [{"code": "M-001", "name": "CNC Mill",
                                                   "machine_type": "CNC"}],
                                     "thresholds": {"CNC": {"temp_max": 85.0,
                                                            "vibration_max": 5.0,
                                                            "current_max": 10.0,
                                                            "rpm_min": 1300.0}}}}
        if path == "/ai/autonomy":
            return 200, {"autonomy": "FAST"}
        if path == "/users":
            return 200, [{"role": "MANAGER", "active": True,
                          "email": "boss@example.com", "name": "Secret Person"},
                         {"role": "OPERATOR", "active": True, "email": "op@example.com"}]
        if path == "/ai/proposals":
            return 200, [{"recommendation": "Schedule repair on M-001", "status": "PENDING"}]
        if path == "/plans/p1/progress":
            return 200, {"plan": {"id": "p1", "title": "Week 42 batch", "status": "IN_PROGRESS",
                                  "progress": 0.5, "flags": [],
                                  "counts": {"done": 1, "active": 1, "pending": 0}},
                         "items": [{"task": {"name": "Mill brackets", "status": "IN_PROGRESS"},
                                    "blocked": False, "overdue": False, "deleted": False}],
                         "timeline": []}
        return 404, "no mock"

    async def fake_post(path, body=None):
        if path == "/ai/proposals":
            return 200, {"id": "p1-test"}
        if path == "/ai/commands/task":
            return 200, {"command_id": "c1", "summary": "Done: CNC operation task assigned to Ravi Kumar on M-001, due tomorrow 6 PM. Note: no order linked.",
                         "warnings": ["no order linked"], "undo_available": True,
                         "created": {"task_id": "t-new"}, "needs_question": None}
        if path == "/ai/commands/order":
            return 200, {"command_id": "c2", "summary": "Done: order ORD-010 for 50 gear housings created.",
                         "warnings": [], "undo_available": True,
                         "created": {"order_id": "o-new", "order_number": "ORD-010"}, "needs_question": None}
        if path == "/ai/commands/change":
            return 200, {"command_id": "c3", "summary": "Done: Mill brackets - priority URGENT.",
                         "warnings": [], "undo_available": True, "created": {"task_id": "t1"},
                         "needs_question": None}
        if path == "/ai/commands/undo-last":
            return 200, {"undone": True, "summary": "Undone: Done: Mill brackets - priority URGENT.", "command_id": "c4"}
        if path.startswith("/ai/analyze-incident/"):
            return 200, {"root_cause": {"summary": "mock cause", "confidence": 0.8},
                         "recommendations": []}
        return 404, "no mock"

    T.api_get, T.api_post = fake_get, fake_post
    import rest as rest_mod
    rest_mod.api_get, rest_mod.api_post = fake_get, fake_post
    tools = T.IndAITools(lambda: None).tools()
    by_name = {}
    for t in tools:
        by_name[getattr(t, "id", getattr(t, "__name__", "?"))] = t
    print("tools:", sorted(by_name))
    assert len(by_name) == 29, f"expected 29 tools, got {len(by_name)}"
    assert "navigate_ui" in by_name
    assert "end_session" in by_name
    for _c in ("do_assign_task", "do_create_order", "do_change_task", "undo_last"):
        assert _c in by_name, f"missing composite tool {_c}"

    ctx = None  # tools under test don't touch context
    r = await by_name["list_available_employees"](ctx, skill="CNC")
    assert "Arun" in r, r
    print("PASS list_available_employees:", r[:80])
    r = await by_name["get_machine_status"](ctx, machine="M-001")
    assert "M-001" in r, r
    print("PASS get_machine_status:", r[:80])
    r = await by_name["list_unassigned_tasks"](ctx)
    assert "Mill brackets" in r, r
    print("PASS list_unassigned_tasks:", r[:80])
    r = await by_name["suggest_assignment"](ctx, task="Mill brackets")
    assert "Arun" in r, r
    print("PASS suggest_assignment:", r[:80])
    r = await by_name["propose_assignment"](ctx, task="Mill brackets", employee="Arun")
    assert "waiting for the admin" in r, r
    print("PASS propose_assignment:", r[:80])
    r = await by_name["navigate_ui"](ctx, action="bogus_action")
    assert "Unknown screen action" in r, r
    print("PASS navigate_ui rejects unknown:", r[:60])
    r = await by_name["navigate_ui"](ctx, action="select_machine", machine="M-001")
    assert "No live room" in r, r
    print("PASS navigate_ui no-room:", r[:60])

    # ---- navigate_ui: alias resolution, filters, one short sentence ----
    import json as _json
    calls = []

    class _FakeLocal:
        async def perform_rpc(self, destination_identity=None, method=None, payload=None,
                              response_timeout=None, **kwargs):
            calls.append((destination_identity, method, payload))
            return "ok"

    class _FakePeer:
        identity = "admin-1"

    class _FakeRoom:
        remote_participants = {"admin-1": _FakePeer()}
        local_participant = _FakeLocal()

    room_tools = T.IndAITools(lambda: _FakeRoom())
    rn = {getattr(t, "id", getattr(t, "__name__", "?")): t for t in room_tools.tools()}

    async def nav_case(phrase, expect, expect_payload, filter_arg=""):
        calls.clear()
        r = await rn["navigate_ui"](ctx, action="navigate", page=phrase, filter=filter_arg)
        assert r == expect, (phrase, r, expect)
        sent = _json.loads(calls[-1][2])
        assert sent == expect_payload, (sent, expect_payload)
        print(f"PASS navigate_ui '{phrase}' -> {r}")

    await nav_case("the machines tab", "Opening Machines.",
                   {"action": "navigate", "page": "machines"})
    await nav_case("go to production", "Opening Production.",
                   {"action": "navigate", "page": "production"})
    await nav_case("take me to employees", "Opening Employees.",
                   {"action": "navigate", "page": "employees"})
    await nav_case("show work plans progress tracker", "Opening Work Plans: progress tracker.",
                   {"action": "navigate", "page": "plans", "filter": "progress"})
    await nav_case("open incidents", "Opening Incidents: open only.",
                   {"action": "navigate", "page": "incidents", "filter": "OPEN"})
    await nav_case("incidents", "Opening Incidents: open only.",
                   {"action": "navigate", "page": "incidents", "filter": "OPEN"},
                   filter_arg="unresolved")
    # Unknown page: spoken answer, at most three suggestions, NO screen touch.
    calls.clear()
    r = await rn["navigate_ui"](ctx, action="navigate", page="open the banana page")
    assert r.startswith("I don\'t have a page called"), r
    assert len(r.split("I can open: ")[1].split(", ")) <= 3, r
    assert not calls, "unknown page must not reach the browser"
    print("PASS navigate_ui unknown page:", r[:90])
    # Fuzzy near-miss: STT typos resolve to a clear winner, one sentence.
    for phrase, expect_page, expect_say in [
        ("go to orders tab", {"action": "navigate", "page": "orders"}, "Opening Orders."),
        ("order tab", {"action": "navigate", "page": "orders"}, "Opening Orders."),
        ("orders tub", {"action": "navigate", "page": "orders"}, "Opening Orders."),
        ("ordas tab", {"action": "navigate", "page": "orders"}, "Opening Orders."),
        ("go to machine tab", {"action": "navigate", "page": "machines"}, "Opening Machines."),
        ("take me to production", {"action": "navigate", "page": "production"}, "Opening Production."),
        ("go to employees", {"action": "navigate", "page": "employees"}, "Opening Employees."),
    ]:
        calls.clear()
        r = await rn["navigate_ui"](ctx, action="navigate", page=phrase)
        assert r == expect_say, (phrase, r, expect_say)
        assert _json.loads(calls[-1][2]) == expect_page, (phrase, calls[-1][2])
        print(f"PASS navigate_ui fuzzy '{phrase}' -> {r}")
    # "other step" must NOT guess: no screen touch, at most three options.
    calls.clear()
    r = await rn["navigate_ui"](ctx, action="navigate", page="go to other step")
    assert "I don't have a page called" in r, r
    assert len(r.split("I can open: ")[1].split(", ")) <= 3, r
    assert not calls, "ambiguous phrase must not reach the browser"
    print("PASS navigate_ui ambiguous 'other step':", r[:90])
    # end_session: explicit requests only, one closing line, browser signalled.
    calls.clear()
    r = await rn["end_session"](ctx)
    assert r == "Okay, ending the session.", r
    assert calls and calls[-1][1] == "voice.end_session", calls
    print("PASS end_session ->", r)
    # No turn may produce "disconnecting" without an end request.
    for phrase in ["go to orders tab", "go to machine tab", "go to other step",
                   "open the banana page"]:
        r = await rn["navigate_ui"](ctx, action="navigate", page=phrase)
        assert "disconnecting" not in r.lower(), (phrase, r)
    print("PASS no 'disconnecting' without an end request")
    # Bad filter / missing page: spoken, actionable.
    r = await rn["navigate_ui"](ctx, action="navigate", page="incidents", filter="banana")
    assert r.startswith("I can\'t filter Incidents"), r
    print("PASS navigate_ui bad filter:", r[:80])
    r = await rn["navigate_ui"](ctx, action="navigate")
    assert r.startswith("Which page?"), r
    print("PASS navigate_ui missing page:", r[:70])
    # Compound entity actions: one sentence + strict (field-limited) payload.
    for action, kw, expect, want in [
        ("select_machine", {"machine": "M-001"}, "Opening Machines.",
         {"action": "select_machine", "machine": "M-001"}),
        ("open_incident", {"incident": "M-001"}, "Opening Incidents.",
         {"action": "open_incident", "incident": "M-001"}),
        ("show_proposals", {}, "Opening AI Assistant.", {"action": "show_proposals"}),
    ]:
        calls.clear()
        r = await rn["navigate_ui"](ctx, action=action, **kw)
        assert r == expect, (action, r)
        assert _json.loads(calls[-1][2]) == want, (action, calls[-1][2])
        print(f"PASS navigate_ui {action} -> {r}")
    # Inapplicable args are dropped (the browser validator rejects them).
    calls.clear()
    await rn["navigate_ui"](ctx, action="select_machine", machine="M-001", order="ORD-001")
    assert _json.loads(calls[-1][2]) == {"action": "select_machine", "machine": "M-001"}
    print("PASS navigate_ui drops inapplicable fields")
    # recent-entities store remembers the last page.
    await rn["navigate_ui"](ctx, action="navigate", page="machines")
    assert room_tools.last and room_tools.last["kind"] == "page" \
        and room_tools.last["id"] == "machines", room_tools.last
    print("PASS navigate_ui updates recent store:", room_tools.last)
    # Composite FAST command tools: one call -> one sentence.
    r = await by_name["do_assign_task"](ctx, person="Ravi Kumar", task_text="CNC operation")
    assert "assigned to Ravi Kumar" in r and "no order linked" in r, r
    print("PASS do_assign_task:", r)
    r = await by_name["do_create_order"](ctx, product="gear housings", quantity=50, customer="Acme")
    assert "ORD-010" in r and "gear housings" in r, r
    print("PASS do_create_order:", r)
    r = await by_name["do_change_task"](ctx, task_ref="Mill brackets", priority="URGENT")
    assert "priority URGENT" in r, r
    print("PASS do_change_task:", r)
    r = await by_name["undo_last"](ctx)
    assert "Undone" in r, r
    print("PASS undo_last:", r)
    # Session memory: remember + pronoun recall (no API needed).
    inst = T.IndAITools(lambda: None)
    by2 = {}
    for t in inst.tools():
        by2[getattr(t, "id", getattr(t, "__name__", "?"))] = t
    inst.remember("task", "t1", "Mill brackets")
    inst.remember("employee", "e1", "Arun Prakash")
    kind, entry = inst.recall("what's the status of that task?")
    assert kind == "task" and entry["id"] == "t1", (kind, entry)
    print("PASS recall that-task:", entry)
    kind, entry = inst.recall("how is he doing?")
    assert kind == "employee" and entry["id"] == "e1", (kind, entry)
    print("PASS recall him:", entry)
    kind, entry = inst.recall("M-001")
    assert kind is None and entry is None, (kind, entry)
    print("PASS explicit ref skips recall")
    # get_task_status via recalled task (mocked REST below).
    r = await by2["get_task_status"](ctx, ref="that task")
    assert "IN_PROGRESS" in r and "50%" in r and "EMP-005" in r, r
    print("PASS get_task_status:", r[:100])
    r = await by2["get_recent_actions"](ctx, limit=5)
    assert "Arun Prakash started" in r, r
    print("PASS get_recent_actions:", r[:100])
    r = await by2["get_plan_status"](ctx, plan_ref="Week 42")
    assert "Week 42 batch" in r and "50%" in r, r
    print("PASS get_plan_status:", r[:100])
    r = await by2["get_worker_progress"](ctx, employee_ref="Arun")
    assert "open" in r and "finished" in r, r
    print("PASS get_worker_progress:", r[:100])

    # ---- new read tools (page data coverage) ----
    r = await by_name["get_production_summary"](ctx)
    assert "40 of 100 units (40%)" in r, r
    print("PASS get_production_summary:", r)
    r = await by_name["get_iot_status"](ctx)
    assert "Stale" in r and "M-001" in r, r
    print("PASS get_iot_status:", r)
    r = await by_name["get_reports_summary"](ctx)
    assert "3 order(s) completed" in r and "M-001 CNC Mill" in r, r
    print("PASS get_reports_summary:", r)
    r = await by_name["get_factory_profile_summary"](ctx)
    assert "CNC / Mechanical" in r and "85.0 C" in r and "FAST" in r, r
    print("PASS get_factory_profile_summary:", r)
    r = await by_name["get_users_summary"](ctx)
    assert "1 manager" in r and "2 active" in r, r
    assert "@" not in r and "Secret Person" not in r, r
    print("PASS get_users_summary (no emails/names):", r)
    r = await by_name["list_pending_proposals"](ctx)
    assert "Schedule repair on M-001" in r, r
    print("PASS list_pending_proposals:", r)

    # ---- scripted multi-turn: phrase -> tool call -> one-sentence reply ----
    from agent import capabilities_line
    names = [getattr(t, "id", getattr(t, "__name__", "")) for t in tools]
    caps = capabilities_line(names)
    assert "\n" not in caps, caps
    turns = [
        ("navigate to the Machines tab",
         {"action": "navigate", "page": "navigate to the Machines tab"}, "Opening Machines."),
        ("go to production",
         {"action": "navigate", "page": "go to production"}, "Opening Production."),
        ("take me to employees",
         {"action": "navigate", "page": "take me to employees"}, "Opening Employees."),
        ("show work plans progress tracker",
         {"action": "navigate", "page": "show work plans progress tracker"},
         "Opening Work Plans: progress tracker."),
        ("open the incident for M-001",
         {"action": "open_incident", "incident": "M-001"}, "Opening Incidents."),
    ]
    for phrase, kwargs, expect in turns:
        r = await rn["navigate_ui"](ctx, **kwargs)
        assert r == expect, (phrase, r, expect)
        print(f"PASS turn '{phrase}' -> {r}")
    for need in ("open any page", "live factory data", "assign and change tasks",
                 "create orders", "undo my last command", "what-if proposals",
                 "deleting records"):
        assert need in caps, (need, caps)
    print("PASS turn 'what can you do?' ->", caps)
    r = await rn["navigate_ui"](ctx, action="navigate", page="open the banana page")
    assert r.startswith("I don\'t have a page called banana page"), r
    print("PASS turn 'open the banana page' ->", r)

    print("ALL MOCKED TESTS PASS")


async def _live():
    import tools as T
    tools = T.IndAITools(lambda: None).tools()
    by_name = {getattr(t, "id", getattr(t, "__name__", "?")): t for t in tools}
    for name, kwargs in [
        ("get_factory_overview", {}),
        ("list_machines_needing_attention", {}),
        ("list_open_incidents", {}),
        ("list_available_employees", {"skill": "Welding"}),
        ("list_unassigned_tasks", {}),
        ("get_recent_actions", {}),
        ("get_production_summary", {}),
        ("get_iot_status", {}),
        ("get_reports_summary", {}),
        ("get_factory_profile_summary", {}),
        ("get_users_summary", {}),
        ("list_pending_proposals", {}),
    ]:
        r = await by_name[name](None, **kwargs)
        print(f"LIVE {name}:", str(r)[:160])
    # navigate_ui against the live API: resolution runs before the room check.
    r = await by_name["navigate_ui"](None, action="navigate", page="open the banana page")
    assert "I don\'t have a page called" in str(r), r
    print("LIVE navigate_ui unknown page:", str(r)[:160])
    r = await by_name["navigate_ui"](None, action="navigate", page="the machines tab")
    assert "No live room" in str(r), r
    print("LIVE navigate_ui (no room):", str(r)[:160])


if __name__ == "__main__":
    if "--live" in sys.argv:
        asyncio.run(_live())
    else:
        asyncio.run(_mocked())
