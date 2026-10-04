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
    assert len(by_name) == 22, f"expected 22 tools, got {len(by_name)}"
    assert "navigate_ui" in by_name
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
    ]:
        r = await by_name[name](None, **kwargs)
        print(f"LIVE {name}:", str(r)[:160])


if __name__ == "__main__":
    if "--live" in sys.argv:
        asyncio.run(_live())
    else:
        asyncio.run(_mocked())
