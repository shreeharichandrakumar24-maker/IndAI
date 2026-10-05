"""Unit tests for the deterministic pre-LLM router + never-silent watchdog.

Run:  venv python src/test_router.py
No network, no LiveKit room, no LLM needed (a fake room/session drives the
async paths). Failing-LLM and hanging-LLM turns are simulated by calling the
agent hook directly with a stub session: the LLM is never even constructed.
"""
import asyncio
import sys
import time

sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else ".")

import router as R

PASS = 0


def ok(label):
    global PASS
    PASS += 1
    print(f"PASS {label}")


def check(cond, label, extra=""):
    assert cond, f"FAIL {label} {extra}"
    ok(label)


# --------------------------------------------------------------------------
# 1. Pure classification: 40+ utterances
# --------------------------------------------------------------------------
def _kind(text):
    r = R.route_turn(text)
    return None if r is None else (r["kind"], r.get("kwargs"))


NAV = [
    # (utterance, expected navigate_ui kwargs subset)
    ("go to employee tab", {"action": "navigate", "page": "employee tab"}),
    ("Go to employee tab.", {"action": "navigate", "page": "employee tab"}),
    ("go to the orders tab", {"action": "navigate", "page": "orders tab"}),
    ("take me to machines", {"action": "navigate", "page": "machines"}),
    ("open production", {"action": "navigate", "page": "production"}),
    ("employee list tab", {"action": "navigate", "page": "employee list tab"}),
    ("employees", {"action": "navigate", "page": "employees"}),
    ("staff", {"action": "navigate", "page": "staff"}),
    ("navigate to reports", {"action": "navigate", "page": "reports"}),
    ("switch to the ai assistant", {"action": "navigate", "page": "ai assistant"}),
    ("jump to tasks", {"action": "navigate", "page": "tasks"}),
    ("show me the factory map", {"action": "navigate", "page": "factory map"}),
    ("open the banana page", {"action": "navigate", "page": "banana page"}),
    ("go to other step", {"action": "navigate", "page": "other step"}),
    ("ordas tab", {"action": "navigate", "page": "ordas tab"}),
    ("open the progress tracker", {"action": "navigate", "page": "progress tracker"}),
    ("show work plans progress tracker", {"action": "navigate", "page": "work plans progress tracker"}),
    ("go to machines", {"action": "navigate", "page": "machines"}),
    ("open incidents", {"action": "navigate", "page": "incidents"}),
    ("show open incidents", {"action": "navigate", "page": "incidents", "filter": "OPEN"}),
    ("open the incident for M-001", {"action": "open_incident", "incident": "M-001"}),
    ("show me M-001", {"action": "select_machine", "machine": "M-001"}),
    ("show me m 002", {"action": "select_machine", "machine": "M-002"}),
    ("open ORD-004", {"action": "open_order", "order": "ORD-004"}),
    ("show pending proposals", {"action": "show_proposals"}),
    ("go to jarvis", {"action": "navigate", "page": "jarvis"}),
    ("take me to production", {"action": "navigate", "page": "production"}),
]

for phrase, want in NAV:
    got = _kind(phrase)
    check(got is not None and got[0] == "tool", f"routes '{phrase}'", got)
    for k, v in want.items():
        check(got[1].get(k) == v, f"kwarg {k} for '{phrase}'", got[1])
ok(f"navigation routing: {len(NAV)} utterances")

UNDO = ["undo that", "undo", "cancel that", "revert that", "please undo that", "undo that."]
for phrase in UNDO:
    check(_kind(phrase) == ("undo", None), f"undo '{phrase}'")
ok(f"undo routing: {len(UNDO)} utterances")

END = ["goodbye Jarvis", "goodbye", "bye Jarvis", "end session", "end the session",
       "stop listening", "disconnect", "disconnect Jarvis", "end voice", "Goodbye Jarvis."]
for phrase in END:
    check(_kind(phrase) == ("end", None), f"end '{phrase}'")
ok(f"end routing: {len(END)} utterances")

# Must reach the LLM (None): data questions, commands, chatter.
TO_LLM = [
    "which machines need attention?",
    "what's happening in production?",
    "which incidents are open?",
    "show me the status of M-001",
    "what is the temperature of M-001?",
    "assign welding to Ravi",
    "create an order for 50 gears",
    "which employees are available for welding?",
    "why is my order late?",
    "what can you do?",
    "hello Jarvis",
    "thank you",
    "",
    "   ",
    "cancel my order please",
    "delete the task",
    "who is working on the mill brackets?",
]
for phrase in TO_LLM:
    check(_kind(phrase) is None, f"to-LLM '{phrase}'", _kind(phrase))
ok(f"LLM fallthrough: {len(TO_LLM)} utterances")

# Fragment merge: short first turn + continuation inside 1.5 s.
t0 = time.monotonic()
check(R.should_merge("employ", t0, "ee tab", t0 + 0.8) == "employ ee tab", "merge fragment")
check(R.should_merge("go to", t0, "banana page", t0 + 0.5) == "go to banana page", "merge split command")
check(R.should_merge("go to", t0, "employee tab", t0 + 5.0) is None, "no merge after window")
check(R.should_merge("which machines need attention please sir", t0, "and also orders", t0 + 0.5) is None,
      "no merge for long first turn")
check(R.should_merge("", t0, "orders", t0 + 0.5) is None, "no merge empty prev")
check(R.should_merge("orders", t0, "show me M-001", t0 + 0.5) is None, "no merge when current routes alone")
ok("fragment merge rules")


# --------------------------------------------------------------------------
# 2. Fake room/session harness for async paths
# --------------------------------------------------------------------------
class FakeLocal:
    def __init__(self, script):
        self.script = list(script)  # "ok" | Exception instances
        self.calls = []

    async def perform_rpc(self, destination_identity=None, method=None, payload=None,
                          response_timeout=None):
        self.calls.append((destination_identity, method, payload, response_timeout))
        nxt = self.script.pop(0) if self.script else "ok"
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt


class FakePeer:
    def __init__(self, identity):
        self.identity = identity


class FakeRoom:
    def __init__(self, peers, local):
        self.remote_participants = {p.identity: p for p in peers}
        self.local_participant = local


class FakeSession:
    def __init__(self):
        self.said = []

    def say(self, text):
        self.said.append(text)
        return object()


class FakeMsg:
    def __init__(self, text):
        self.text_content = text


def _tools(room):
    import tools as T
    inst = T.IndAITools(lambda: room)
    return {getattr(t, "id", getattr(t, "__name__", "?")): t for t in inst.tools()}


async def _async():
    # -- routed navigation speaks ONE sentence through the real tool --
    local = FakeLocal(["ok"])
    room = FakeRoom([FakePeer("admin-1")], local)
    tools = _tools(room)
    out = await R.execute_route(
        {"kind": "tool", "kwargs": {"action": "navigate", "page": "go to employee tab"}}, tools)
    check(out == "Opening Employees.", "execute navigate employee tab", out)
    import json as _json
    check(_json.loads(local.calls[0][2]) == {"action": "navigate", "page": "employees"},
          "RPC payload is canonical page id", local.calls[0][2])
    check(local.calls[0][3] == 3.0, "RPC bounded by 3 s timeout", local.calls[0])
    ok("router execute navigate")

    # -- RPC failure modes each produce a short spoken message --
    room2 = FakeRoom([], FakeLocal(["ok"]))
    out = await R.execute_route(
        {"kind": "tool", "kwargs": {"action": "navigate", "page": "orders"}}, _tools(room2))
    check("No admin browser" in out, "no-participant message", out)
    ok("RPC no-participant")

    room3 = FakeRoom([FakePeer("admin-1")], FakeLocal([RuntimeError("boom-shakalaka")]))
    out = await R.execute_route(
        {"kind": "tool", "kwargs": {"action": "navigate", "page": "orders"}}, _tools(room3))
    check("could not be updated" in out and "boom" not in out, "RPC error message", out)
    ok("RPC error")

    room4 = FakeRoom([FakePeer("admin-1")], FakeLocal([asyncio.TimeoutError("timed out waiting")]))
    out = await R.execute_route(
        {"kind": "tool", "kwargs": {"action": "navigate", "page": "orders"}}, _tools(room4))
    check("too long" in out, "RPC timeout message", out)
    ok("RPC timeout")

    # -- participant appears on retry (real lookup-retry loop) --
    late = FakeRoom([], FakeLocal(["ok"]))
    import tools as T
    inst = T.IndAITools(lambda: late)

    async def _join_late():
        await asyncio.sleep(0.5)  # appears during the 2nd lookup attempt
        late.remote_participants = {"admin-9": FakePeer("admin-9")}

    by = {getattr(t, "id", getattr(t, "__name__", "?")): t for t in inst.tools()}
    join_task = asyncio.create_task(_join_late())
    out = await by["navigate_ui"](None, action="navigate", page="go to machines")
    await join_task
    check(out == "Opening Machines.", "retry then navigate", out)
    ok("RPC lookup retry")

    # -- undo + end through the router (backend/room faked) --
    async def fake_undo(ctx):
        return "Undone: test command."
    out = await R.execute_route({"kind": "undo"}, {"undo_last": fake_undo})
    check(out == "Undone: test command.", "execute undo", out)
    ok("router execute undo")

    # -- hook level: navigation works with NO LLM at all --
    # Agent.session is a read-only property (resolves via the live activity);
    # stub it at class level for these offline tests (production untouched).
    import agent as A
    from livekit.agents.voice.agent import Agent as _Agent

    _orig_session_prop = _Agent.session
    # NOTE: agents are constructed BEFORE patching: Agent.__init__ inspects
    # the (read-only) session property itself.
    ag = A.JarvisAgent(lambda: room)
    ag2 = A.JarvisAgent(lambda: room)
    ag3 = A.JarvisAgent(lambda: None)
    ag4 = A.JarvisAgent(lambda: None)
    ag0 = A.JarvisAgent(lambda: room)
    _Agent.session = property(
        lambda self: self.__dict__.get("_stub_session") or (_ for _ in ()).throw(
            RuntimeError("agent not running")))
    if True:  # hook tests below run with the stubbed session; restored in finally
        ag.__dict__["_stub_session"] = FakeSession()
        by2 = _tools(room)
        ag._tools_by_name = by2
        try:
            await ag.on_user_turn_completed(None, FakeMsg("go to employee tab"))
            check(False, "hook must StopResponse on routed turn")
        except Exception as e:
            check(type(e).__name__ == "StopResponse", "hook raises StopResponse", type(e).__name__)
        said = ag.__dict__["_stub_session"].said
        check(said == ["Opening Employees."], "hook speaks one sentence", said)
        ok("hook routes with LLM absent")

    # -- hook level: ambiguous/unknown WITH verb -> spoken <=3-option question --
    ag2.__dict__["_stub_session"] = FakeSession()
    ag2._tools_by_name = by2
    try:
        await ag2.on_user_turn_completed(None, FakeMsg("go to other step"))
    except Exception as e:
        check(type(e).__name__ == "StopResponse", "ambiguous StopResponse")
    said2 = ag2.__dict__["_stub_session"].said
    check(len(said2) == 1 and "I can open:" in said2[0], "ambiguous spoken", said2)
    check(len(said2[0].split("I can open: ")[1].split(", ")) <= 3, "ambiguous <=3 options")
    ok("hook ambiguous question")

    # -- watchdog: simulated LLM hang (no speech ever) -> fallback spoken --
    import agent as A2
    old_wd = A2.WATCHDOG_S
    A2.WATCHDOG_S = 0.2
    try:
        ag3.__dict__["_stub_session"] = FakeSession()
        await ag3.on_user_turn_completed(None, FakeMsg("which machines need attention?"))
        await asyncio.sleep(0.6)
        said3 = ag3.__dict__["_stub_session"].said
        check(any("took too long" in s for s in said3), "watchdog speaks on hang", said3)
        ok("watchdog on hung turn")
        # -- watchdog stands down when speech started (simulated agent speech) --
        ag4.__dict__["_stub_session"] = FakeSession()
        await ag4.on_user_turn_completed(None, FakeMsg("tell me about production"))
        ag4._mark_spoken()  # speech started before the deadline
        await asyncio.sleep(0.6)
        said4 = ag4.__dict__["_stub_session"].said
        check(said4 == [], "watchdog quiet after speech", said4)
        ok("watchdog stands down on speech")
        # -- hook never mutates the (read-only) chat context --
        from livekit.agents import llm as _llmmod
        _orig_add = _llmmod.ChatContext.add_message

        def _boom(self, *a, **k):
            raise RuntimeError("trying to modify a read-only chat context")

        _llmmod.ChatContext.add_message = _boom
        try:
            ag0.__dict__["_stub_session"] = FakeSession()
            ag0._tools_by_name = by2
            try:
                await ag0.on_user_turn_completed(None, FakeMsg("go to machine tab"))
                check(False, "hook must StopResponse")
            except Exception as e:
                check(type(e).__name__ == "StopResponse", "StopResponse with read-only ctx")
            said0 = ag0.__dict__["_stub_session"].said
            check(said0 == ["Opening Machines."], "hook speaks despite read-only ctx", said0)
            ok("hook never touches chat_ctx")
        finally:
            _llmmod.ChatContext.add_message = _orig_add
    finally:
        A2.WATCHDOG_S = old_wd
        _Agent.session = _orig_session_prop

    # -- stale browser handler: one retry heals the turn --
    stale = FakeRoom([FakePeer("admin-1")],
                     FakeLocal(["rejected: voice command handler reloading, please retry", "ok"]))
    out = await R.execute_route(
        {"kind": "tool", "kwargs": {"action": "navigate", "page": "go to machines"}},
        _tools(stale))
    check(out == "Opening Machines.", "stale-handler retry heals turn", out)
    check(len(stale.local_participant.calls) == 2, "retry re-issues one RPC")
    ok("RPC stale-handler retry")

    # -- stale handler that never recovers: still speaks (no silence) --
    dead = FakeRoom([FakePeer("admin-1")],
                    FakeLocal(["rejected: voice command handler reloading, please retry",
                               "rejected: voice command handler reloading, please retry"]))
    out = await R.execute_route(
        {"kind": "tool", "kwargs": {"action": "navigate", "page": "go to machines"}},
        _tools(dead))
    check(isinstance(out, str) and len(out) > 0, "persistent stale handler still speaks", out)
    ok("RPC persistent-stale speaks")

    # -- capped lists state the TRUE total (never mistake shown for total) --
    import tools as _Tmod
    _orig_get = _Tmod.rest.api_get
    _emps10 = [{"id": f"e{i}", "name": f"Worker {i}", "role": "CNC Operator",
                "availability": "AVAILABLE", "shift": "Morning",
                "skills": {"items": ["CNC operation"]}} for i in range(10)]
    _tasks10 = [{"id": f"t{i}", "name": f"Job {i}", "status": "PENDING",
                 "required_skill": "CNC operation", "employee_id": None} for i in range(10)]

    async def _fake_get(path, params=None):
        if path == "/employees":
            return 200, _emps10
        if path == "/tasks":
            return 200, _tasks10
        if path.endswith("/worker-login"):
            return 200, {"has_login": True, "employee_code": "EMP-001"}
        return 404, "no mock"

    _Tmod.rest.api_get = _fake_get
    try:
        byT = {getattr(t, "id", getattr(t, "__name__", "?")): t for t in _Tmod.IndAITools(lambda: None).tools()}
        r = await byT["list_available_employees"](None)
        check("(10 total.)" in r, "employees total stated", r[:120])
        check("Worker 9" not in r, "employees list still capped at 8", r[:200])
        r = await byT["list_unassigned_tasks"](None)
        check("(10 total.)" in r, "tasks total stated", r[:120])
        ok("capped lists state totals")
    finally:
        _Tmod.rest.api_get = _orig_get

    # -- timing: 20 routed turns, turn-completion -> sentence (excl STT/TTS) --
    dt = []
    for _ in range(20):
        t0 = time.perf_counter()
        r = R.route_turn("go to employee tab")
        s = await R.execute_route(r, tools)
        dt.append(time.perf_counter() - t0)
        assert s == "Opening Employees."
    dt.sort()
    p50, p95 = dt[len(dt) // 2], dt[int(len(dt) * 0.95) - 1]
    print(f"TIMING router p50={p50 * 1000:.1f}ms p95={p95 * 1000:.1f}ms n=20")
    check(p95 < 1.0, "router p95 well under 1 s")
    ok("router timing")


asyncio.run(_async())
print(f"\n{PASS} checks passed")
