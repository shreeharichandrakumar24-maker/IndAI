"""IndAI Jarvis function tools (read + propose-only). No approve/execute tool.

Memory model (Part 2):
- `recent`: per-session store (this object lives for one agent session) of
  the last task, order, employee, machine, incident, proposal and plan seen
  in tool results, plus a global `last` pointer. Pronouns ("that task",
  "him", "the last proposal", "it") resolve here BEFORE any other lookup.
- Every tool output names the entity AND carries its internal id in
  brackets, e.g. "CNC roughing [id 8f3a...]". Ids are for the MODEL to pass
  back to tools only — the agent instructions forbid speaking them.
- Ambiguous names return at most three labeled options so the model asks
  ONE short clarifying question (per instructions).
"""
from __future__ import annotations

import re
import time

from livekit.agents import RunContext, function_tool

try:
    from . import rest
    from . import navigation as nav
except ImportError:  # loaded as a top-level script (tests, direct runs)
    import rest
    import navigation as nav

_OK = (200, 201)

KINDS = ("task", "order", "employee", "machine", "incident", "proposal", "plan")

# Vague references resolve from the session store, never from search.
_VAGUE_KIND = re.compile(
    r"\b(that|the|this|last|my|current)\b.{0,24}\b"
    r"(task|order|incident|proposal|employee|worker|person|machine|plan)\b",
    re.IGNORECASE,
)
_BARE_PRONOUN = re.compile(r"^(it|him|her|them|that one|the one"
                           r"|the one you (just )?(assigned|mentioned))\s*[?.!]*$",
                           re.IGNORECASE)


def _short(text: object, n: int = 220) -> str:
    s = str(text or "")
    return s if len(s) <= n else s[:n] + "..."


def _tag(label: str, id_: str) -> str:
    """Name plus internal id (model-only, never spoken)."""
    return f"{label} [id {id_}]"


def _recall_kind(text: str):
    """Explicit kind inside a vague reference ("that task", "the last
    proposal", "him"). Returns the kind or None."""
    t = (text or "").lower()
    if re.search(r"\b(last|that|the|this)\s+proposal\b", t):
        return "proposal"
    if re.search(r"\b(last|that|the|this)\s+tasks?\b", t):
        return "task"
    if re.search(r"\b(last|that|the|this)\s+machine\b", t):
        return "machine"
    if re.search(r"\b(last|that|the|this)\s+orders?\b", t):
        return "order"
    if re.search(r"\b(last|that|the|this)\s+incident\b", t):
        return "incident"
    if re.search(r"\b(last|that|the|this)\s+plans?\b", t):
        return "plan"
    if re.search(r"\b(last|that|the|this)\s+(employee|worker|person)\b", t):
        return "employee"
    if re.search(r"\b(him|her|he|she|they)\b", t):
        return "employee"
    return None


class IndAITools:
    """Tools bound to one agent instance (room ref set per job).

    One instance serves ONE voice session, so `recent`/`last` below are
    automatically per-session with no extra plumbing.
    """

    def __init__(self, room_getter):
        self._room_getter = room_getter
        self.recent = {}  # kind -> {id, label}
        self.last = None  # {kind, id, label} — most recent of any kind
        self._at = {}     # kind -> monotonic timestamp (recency order)
        self.recent_command = None  # last command_id from a composite tool

    # ---- session memory primitives ----

    def remember(self, kind: str, id_: str, label: str) -> None:
        if not id_:
            return
        entry = {"kind": kind, "id": str(id_), "label": str(label or kind)}
        self.recent[kind] = entry
        self.last = entry
        self._at[kind] = time.monotonic()

    def forget(self, kind: str, id_: str) -> None:
        cur = self.recent.get(kind)
        if cur and str(cur.get("id")) == str(id_):
            self.recent.pop(kind, None)
        if self.last and self.last.get("kind") == kind \
                and str(self.last.get("id")) == str(id_):
            self.last = None

    def recall(self, text: str):
        """(kind, entry|None). Explicit-kind vague refs hit that kind; bare
        pronouns ("it", "that one") hit the global last entity."""
        kind = _recall_kind(text or "")
        if kind:
            return kind, self.recent.get(kind)
        if _BARE_PRONOUN.match((text or "").strip()):
            if self.last:
                return self.last.get("kind"), self.last
            return None, None
        if _VAGUE_KIND.search(text or ""):
            # "the X" without a stored X: caller falls through to search.
            return kind, self.recent.get(kind) if kind else None
        return None, None

    async def _resolve(self, kind: str, raw: str):
        """Returns (match|None, note). match = {id, label, summary}.
        note is None on a hit, otherwise a speakable clarification string."""
        raw = (raw or "").strip()
        if not raw:
            entry = self.recent.get(kind)
            if entry:
                return {"id": entry["id"], "label": entry["label"],
                        "summary": entry["label"]}, None
            return None, f"Which {kind}? I don't have a recent one in this conversation."
        _, remembered = self.recall(raw)
        if remembered:
            return {"id": remembered["id"], "label": remembered["label"],
                    "summary": remembered["label"]}, None
        try:
            code, data = await rest.api_get("/resolve", params={"type": kind, "q": raw})
        except Exception:
            code, data = 0, None
        if code == 200 and isinstance(data, dict):
            matches = data.get("matches") or []
            if len(matches) == 1:
                m = matches[0]
                self.remember(kind, m["id"], m["label"])
                return m, None
            if len(matches) > 1:
                opts = "; ".join(m["label"] for m in matches[:3])
                return None, f"Which one: {opts}?"
            return None, f"I don't have a {kind} matching {raw}."
        # Resolver unreachable: caller falls back to legacy local matching.
        return None, "fallback"

    # ---- browser RPC helpers (robust: retry lookup, bounded wait) ----

    # Browser RPC bounds: resolve retries + response timeout. A hung screen
    # must produce a short spoken error, never a blocked (silent) turn.
    RPC_TIMEOUT_S = 3.0
    RPC_LOOKUP_RETRIES = 2
    RPC_LOOKUP_DELAY_S = 0.4

    async def _find_browser_target(self):
        """Admin browser participant identity, or None. Retries briefly:
        the browser may still be joining when the turn lands."""
        import asyncio as _asyncio
        room = self._room_getter()
        if room is None:
            return None
        for attempt in range(self.RPC_LOOKUP_RETRIES + 1):
            target = None
            try:
                parts = room.remote_participants.values()
            except Exception:
                parts = []
            try:
                for p in parts:
                    ident = getattr(p, "identity", "") or ""
                    if ident.startswith("admin-"):
                        target = ident
                        break
                if target is None and room.remote_participants:
                    target = next(iter(room.remote_participants.values())).identity
            except Exception:
                target = None
            if target:
                return target
            if attempt < self.RPC_LOOKUP_RETRIES:
                try:
                    await _asyncio.sleep(self.RPC_LOOKUP_DELAY_S)
                except Exception:
                    break
        return None

    def tools(self):
        inner = self

        async def _resolve_or_legacy(kind, raw, legacy):
            """Shared resolve with legacy list-matching fallback (keeps old
            behavior when /api/resolve is unreachable). Returns (match|None,
            speakable-note-or-None). legacy() returns a match dict or None."""
            match, note = await inner._resolve(kind, raw)
            if match is not None or note != "fallback":
                return match, note
            try:
                hit = await legacy()
            except Exception:
                hit = None
            return (hit, None) if hit is not None else (None, None)

        @function_tool()
        async def get_factory_overview(context: RunContext) -> str:
            """Current factory counts: orders, runs, tasks, machines, open incidents, high-risk orders."""
            code, data = await rest.api_get("/ai/assistant/quick/overview")
            if code != 200:
                return "I don't have that information right now."
            d = data if isinstance(data, dict) else {}
            return f"{d.get('summary', 'No overview available.')}"

        @function_tool()
        async def list_machines_needing_attention(context: RunContext) -> str:
            """Machines that are abnormal or have open incidents."""
            code, data = await rest.api_get("/machines")
            if code != 200 or not isinstance(data, list):
                return "I don't have that information right now."
            bad = []
            for m in data:
                if (m.get("health_status") or "").upper() not in ("GOOD", "", None) or m.get("status") in ("MAINTENANCE", "STOPPED"):
                    bad.append(f"{m.get('name')} ({m.get('health_status') or m.get('status')})")
                if len(bad) >= 8:
                    break
            if not bad:
                return "All machines report GOOD health."
            return "Needs attention: " + "; ".join(bad)

        @function_tool()
        async def get_machine_status(context: RunContext, machine: str) -> str:
            """Status, latest readings and open incidents for one machine (code like M-001, spoken "M zero zero one", or name).

            Args:
                machine: Machine code (M-001), name, or "that machine".
            """
            async def legacy():
                code, data = await rest.api_get("/machines")
                if code != 200 or not isinstance(data, list):
                    return None
                want = (machine or "").strip().lower()
                hit = next((m for m in data if want in (m.get("name") or "").lower() or (m.get("name") or "").lower().startswith(want.replace(" ", ""))), None)
                if hit is None:
                    return None
                return {"id": hit["id"], "label": hit.get("name"),
                        "summary": hit.get("name")}
            match, note = await _resolve_or_legacy("machine", machine, legacy)
            if match is None:
                return note or f"I don't have a machine matching {machine}."
            code2, latest = await rest.api_get(f"/telemetry/{match['id']}", params={"limit": 1})
            r = latest[0] if code2 == 200 and isinstance(latest, list) and latest else {}
            code3, incs = await rest.api_get("/incidents", params={"machine_id": match["id"], "status": "OPEN"})
            n_open = len(incs) if code3 == 200 and isinstance(incs, list) else 0
            inner.remember("machine", match["id"], match["label"])
            code4, mrow = await rest.api_get("/machines")
            status = health = ""
            if code4 == 200 and isinstance(mrow, list):
                full = next((m for m in mrow if m.get("id") == match["id"]), {})
                status, health = full.get("status", ""), full.get("health_status", "")
            return (f"{_tag(match['label'], match['id'])}: status {status}, health {health}. "
                    f"Latest: {r.get('temperature', '?')} C, vibration {r.get('vibration', '?')}, "
                    f"current {r.get('current', '?')} A, {r.get('rpm', '?')} rpm. {n_open} open incident(s).")

        @function_tool()
        async def get_order_status(context: RunContext, order_number: str) -> str:
            """Order progress, runs, tasks, machines, employees and risk for one order number.

            Args:
                order_number: The order number, e.g. ORD-001, or "that order".
            """
            async def legacy():
                code, data = await rest.api_get("/orders")
                if code != 200 or not isinstance(data, list):
                    return None
                want = (order_number or "").strip().lower()
                hit = next((o for o in data if (o.get("order_number") or "").lower() == want), None)
                if hit is None:
                    return None
                return {"id": hit["id"], "label": hit.get("order_number"),
                        "summary": hit.get("order_number")}
            match, note = await _resolve_or_legacy("order", order_number, legacy)
            if match is None:
                return note or f"I don't have an order {order_number}."
            code2, tasks = await rest.api_get("/tasks", params={"order_id": match["id"]})
            nt = len(tasks) if code2 == 200 and isinstance(tasks, list) else 0
            inner.remember("order", match["id"], match["label"])
            code3, orow = await rest.api_get("/orders")
            status = deadline = progress = ""
            if code3 == 200 and isinstance(orow, list):
                full = next((o for o in orow if o.get("id") == match["id"]), {})
                status, deadline, progress = full.get("status", ""), full.get("deadline") or "none", full.get("progress", "")
            return (f"Order {_tag(match['label'], match['id'])}: {status}, progress {progress}, "
                    f"deadline {deadline}, {nt} task(s).")

        @function_tool()
        async def list_open_incidents(context: RunContext) -> str:
            """Currently open incidents with severity and machine."""
            code, data = await rest.api_get("/incidents", params={"status": "OPEN"})
            if code != 200 or not isinstance(data, list):
                return "I don't have that information right now."
            if not data:
                return "No open incidents."
            return "; ".join(f"{i.get('severity')} on {(i.get('description') or '')[:80]} [id {i.get('id')}]" for i in data[:8])

        @function_tool()
        async def analyze_incident(context: RunContext, incident_id: str) -> str:
            """AI root cause + risk for one incident. Summarizes, never invents.

            Args:
                incident_id: The incident id (as shown in brackets), or "that incident".
            """
            match, note = await inner._resolve("incident", incident_id)
            iid = match["id"] if match else (incident_id or "").strip()
            if match is None and note and note != "fallback" and "Which" not in (note or ""):
                # Explicit unknown ref (not a vague pronoun we could recall).
                if not inner.recent.get("incident"):
                    return note
                iid = inner.recent["incident"]["id"]
            code, data = await rest.api_post(f"/ai/analyze-incident/{iid}")
            if code == 503:
                return "Analysis is unavailable right now (no AI key on the server)."
            if code == 404:
                inner.forget("incident", iid)
                return "That incident no longer exists."
            if code != 200 or not isinstance(data, dict):
                return "I don't have that information right now."
            rc = data.get("root_cause") or {}
            recs = "; ".join((r.get("recommendation") or "")[:60] for r in data.get("recommendations", [])[:3])
            if match:
                inner.remember("incident", match["id"], match["label"])
            return f"Root cause: {rc.get('summary', 'unknown')} (confidence {rc.get('confidence', '?')}). Suggestions: {recs or 'none'}."

        async def _code_for(employee_id: str) -> str:
            code, data = await rest.api_get(f"/employees/{employee_id}/worker-login")
            if code == 200 and isinstance(data, dict):
                return data.get("employee_code") or ""
            return ""

        @function_tool()
        async def list_available_employees(context: RunContext, skill: str = "") -> str:
            """Employees with status ACTIVE. Optionally filtered by skill text.

            Args:
                skill: Optional skill substring, e.g. Welding.
            """
            code, data = await rest.api_get("/employees")
            if code != 200 or not isinstance(data, list):
                return "I don't have that information right now."
            want = (skill or "").strip().lower()
            out = []
            for e in data:
                if (e.get("availability") or "AVAILABLE").upper() != "AVAILABLE":
                    continue
                if want and want not in str(e.get("skills") or "").lower() and want not in (e.get("role") or "").lower():
                    continue
                emp_code = await _code_for(e.get("id"))
                out.append(f"{e.get('name')}" + (f" ({emp_code})" if emp_code else "") +
                           f" [id {e.get('id')}] ({e.get('role')}, {e.get('shift') or 'no shift'})")
                if len(out) >= 8:
                    break
            if not out:
                return f"No available employees{(' for ' + skill) if skill else ''}."
            return "Available: " + "; ".join(out)

        @function_tool()
        async def get_employee_workload(context: RunContext, employee: str) -> str:
            """Open tasks for one employee (name or employee code like EMP-001).

            Args:
                employee: Employee name, code, or "him"/"her"/"that worker".
            """
            async def legacy():
                code, data = await rest.api_get("/employees")
                if code != 200 or not isinstance(data, list):
                    return None
                want = (employee or "").strip().lower()
                hit = next((e for e in data if want in (e.get("name") or "").lower()), None)
                if hit is None:
                    return None
                return {"id": hit["id"], "label": hit.get("name"), "summary": hit.get("name")}
            match, note = await _resolve_or_legacy("employee", employee, legacy)
            if match is None:
                return note or f"I don't have an employee matching {employee}."
            code2, tasks = await rest.api_get("/tasks", params={"employee_id": match["id"]})
            open_t = [t for t in (tasks if code2 == 200 and isinstance(tasks, list) else [])
                      if (t.get("status") or "").upper() in ("PENDING", "IN_PROGRESS")]
            inner.remember("employee", match["id"], match["label"])
            names = "; ".join(f"{t.get('name', '?')} [id {t.get('id')}]" for t in open_t[:5])
            return f"{_tag(match['label'], match['id'])}: {len(open_t)} open task(s). " + names

        @function_tool()
        async def list_unassigned_tasks(context: RunContext) -> str:
            """Tasks with no employee assigned."""
            code, data = await rest.api_get("/tasks")
            if code != 200 or not isinstance(data, list):
                return "I don't have that information right now."
            un = [t for t in data if not t.get("employee_id")
                  and (t.get("status") or "").upper() in ("PENDING", "IN_PROGRESS")]
            if not un:
                return "No unassigned tasks."
            return "; ".join(f"{t.get('name')} [id {t.get('id')}] (needs {t.get('required_skill') or 'general'})" for t in un[:8])

        @function_tool()
        async def suggest_assignment(context: RunContext, task: str) -> str:
            """Top ranked workers/machines for one task (name, "welding task for Suresh", or id) with reasons.

            Args:
                task: Task name, natural reference ("that task"), or id.
            """
            async def legacy():
                code, data = await rest.api_get("/tasks")
                if code != 200 or not isinstance(data, list):
                    return None
                want = (task or "").strip().lower()
                hit = next((t for t in data if want in (t.get("name") or "").lower() or t.get("id") == task), None)
                if hit is None:
                    return None
                return {"id": hit["id"], "label": hit.get("name"), "summary": hit.get("name")}
            match, note = await _resolve_or_legacy("task", task, legacy)
            if match is None:
                return note or f"I don't have a task matching {task}."
            inner.remember("task", match["id"], match["label"])
            code2, cands = await rest.api_get("/allocation/candidates", params={"task_id": match["id"]})
            if code2 != 200 or not isinstance(cands, dict):
                return f"Task {match['label']}: no candidate data right now."
            emps = (cands.get("employees") or [])[:3]
            if not emps:
                return f"Task {match['label']}: no eligible worker found."
            return f"Task {_tag(match['label'], match['id'])}: " + "; ".join(
                f"{e.get('name')} [id {e.get('id')}] ({e.get('open_tasks', 0)} open)" for e in emps)

        @function_tool()
        async def propose_assignment(context: RunContext, task: str, employee: str, machine: str = "", reason: str = "") -> str:
            """Propose assigning a task to a worker (PENDING only). Returns the proposal id.

            Args:
                task: Task name, natural reference, or id.
                employee: Employee name, code (EMP-001), id, or "him"/"her".
                machine: Optional machine code or id.
                reason: Why this pairing fits.
            """
            async def legacy_task():
                code, data = await rest.api_get("/tasks")
                if code != 200 or not isinstance(data, list):
                    return None
                tw = task.strip().lower()
                trow = next((t for t in data if tw in (t.get("name") or "").lower() or t.get("id") == task), None)
                if trow is None:
                    return None
                return {"id": trow["id"], "label": trow.get("name"), "summary": trow.get("name")}
            tmatch, tnote = await _resolve_or_legacy("task", task, legacy_task)
            if tmatch is None:
                return tnote or f"I don't have a task matching {task}."

            async def legacy_emp():
                code2, emps = await rest.api_get("/employees")
                ew = employee.strip().lower()
                erow = next((e for e in (emps if code2 == 200 and isinstance(emps, list) else [])
                             if ew in (e.get("name") or "").lower() or e.get("id") == employee), None)
                if erow is None:
                    return None
                return {"id": erow["id"], "label": erow.get("name"), "summary": erow.get("name")}
            ematch, enote = await _resolve_or_legacy("employee", employee, legacy_emp)
            if ematch is None:
                return enote or f"I don't have an employee matching {employee}."
            mid = None
            mlabel = ""
            if (machine or "").strip():
                async def legacy_mac():
                    code3, macs = await rest.api_get("/machines")
                    mw = machine.strip().lower()
                    mrow = next((m for m in (macs if code3 == 200 and isinstance(macs, list) else [])
                                 if (m.get("name") or "").lower().startswith(mw) or m.get("id") == machine), None)
                    if mrow is None:
                        return None
                    return {"id": mrow["id"], "label": mrow.get("name"), "summary": mrow.get("name")}
                mmatch, mnote = await _resolve_or_legacy("machine", machine, legacy_mac)
                if mmatch is None:
                    return mnote or f"I don't have a machine matching {machine}."
                mid = mmatch["id"]
                mlabel = mmatch["label"]
                inner.remember("machine", mid, mlabel)
            params = {"task_id": tmatch["id"], "employee_id": ematch["id"]}
            if mid:
                params["machine_id"] = mid
            code4, prop = await rest.api_post("/ai/proposals", {
                "action_type": "REASSIGN_TASK",
                "params": params,
                "reason": reason or f"Voice proposal: {task} -> {employee}",
            })
            if code4 != 200 or not isinstance(prop, dict):
                detail = prop.get("detail") if isinstance(prop, dict) else prop
                return f"The proposal was rejected: {_short(detail)}. Nothing changed."
            inner.remember("task", tmatch["id"], tmatch["label"])
            inner.remember("employee", ematch["id"], ematch["label"])
            pid = str(prop.get("id"))
            inner.remember("proposal", pid, f"proposal for {tmatch['label']}")
            return f"Proposal {pid[:8]} is waiting for the admin's approval on screen."

        @function_tool()
        async def propose_maintenance(context: RunContext, machine: str, reason: str = "") -> str:
            """Propose a maintenance record for a machine (PENDING only). Returns the proposal id.

            Args:
                machine: Machine code (M-001), spoken code, or id.
                reason: Why maintenance is needed.
            """
            async def legacy():
                code, names = await rest.api_get("/machines")
                if code != 200 or not isinstance(names, list):
                    return None
                want = machine.strip().lower()
                hit = next((m for m in names if (m.get("name") or "").lower().startswith(want) or m.get("id") == machine), None)
                if hit is None:
                    return None
                return {"id": hit["id"], "label": hit.get("name"), "summary": hit.get("name")}
            match, note = await _resolve_or_legacy("machine", machine, legacy)
            if match is None:
                return note or f"I don't have a machine matching {machine}."
            code2, data = await rest.api_post("/ai/proposals", {
                "action_type": "SCHEDULE_MAINTENANCE",
                "params": {"machine_id": match["id"], "issue": reason or "Voice-requested check"},
                "reason": reason or f"Voice proposal for {machine}",
            })
            if code2 != 200 or not isinstance(data, dict):
                return "The proposal could not be recorded. Nothing changed."
            inner.remember("machine", match["id"], match["label"])
            pid = str(data.get("id"))
            inner.remember("proposal", pid, f"maintenance proposal for {match['label']}")
            return f"Proposal {pid[:8]} is waiting for the admin's approval on screen."

        @function_tool()
        async def propose_delay(context: RunContext, task: str, new_deadline: str, reason: str = "") -> str:
            """Propose moving a task deadline (PENDING only). Returns the proposal id.

            Args:
                task: Task name, natural reference, or id.
                new_deadline: ISO datetime, e.g. 2026-10-20T00:00:00.
                reason: Why the delay is needed.
            """
            async def legacy():
                code, data = await rest.api_get("/tasks")
                if code != 200 or not isinstance(data, list):
                    return None
                want = task.strip().lower()
                hit = next((t for t in data if want in (t.get("name") or "").lower() or t.get("id") == task), None)
                if hit is None:
                    return None
                return {"id": hit["id"], "label": hit.get("name"), "summary": hit.get("name")}
            match, note = await _resolve_or_legacy("task", task, legacy)
            if match is None:
                return note or f"I don't have a task matching {task}."
            code2, data2 = await rest.api_post("/ai/proposals", {
                "action_type": "DELAY_TASK",
                "params": {"task_id": match["id"], "new_deadline": new_deadline},
                "reason": reason or f"Voice proposal to delay {task}",
            })
            if code2 != 200 or not isinstance(data2, dict):
                return "The proposal could not be recorded. Nothing changed."
            inner.remember("task", match["id"], match["label"])
            pid = str(data2.get("id"))
            inner.remember("proposal", pid, f"delay proposal for {match['label']}")
            return f"Proposal {pid[:8]} is waiting for the admin's approval on screen."

        @function_tool()
        async def get_task_status(context: RunContext, ref: str = "") -> str:
            """Live status of one task: progress, worker, machine, deadline, quantity, last update. Empty ref uses "that task".

            Args:
                ref: Task name, natural reference ("that task"), or id. Empty means the recent task.
            """
            match, note = await inner._resolve("task", ref)
            if match is None:
                # Legacy fallback: substring over the task list.
                code, data = await rest.api_get("/tasks")
                want = (ref or "").strip().lower()
                hit = next((t for t in (data if code == 200 and isinstance(data, list) else [])
                            if want and (want in (t.get("name") or "").lower() or t.get("id") == ref)), None)
                if hit is None:
                    if note and note != "fallback":
                        return note
                    return f"I don't have a task matching {ref}."
                match = {"id": hit["id"], "label": hit.get("name"), "summary": hit.get("name")}
            code, t = await rest.api_get(f"/tasks/{match['id']}")
            if code == 404:
                inner.forget("task", match["id"])
                return "That task no longer exists."
            if code != 200 or not isinstance(t, dict):
                return "I don't have that information right now."
            inner.remember("task", t.get("id"), t.get("name"))
            who = "unassigned"
            if t.get("employee_id"):
                c2, e = await rest.api_get(f"/employees/{t['employee_id']}")
                if c2 == 200 and isinstance(e, dict):
                    emp_code = await _code_for(t["employee_id"])
                    who = f"{e.get('name')}" + (f" ({emp_code})" if emp_code else "")
                    inner.remember("employee", t["employee_id"], e.get("name"))
            mac = ""
            if t.get("machine_id"):
                c3, mrow = await rest.api_get("/machines")
                if c3 == 200 and isinstance(mrow, list):
                    m = next((x for x in mrow if x.get("id") == t["machine_id"]), {})
                    mac = f", machine {(m.get('name') or '').split(' ')[0]}"
            qty = ""
            if t.get("order_id"):
                c4, runs = await rest.api_get("/production", params={"order_id": t["order_id"]})
                if c4 == 200 and isinstance(runs, list) and runs:
                    run = next((r for r in runs if r.get("task_id") == t["id"]), runs[0])
                    if run.get("quantity_target"):
                        qty = f" Quantity {run.get('quantity_completed', 0)} of {run.get('quantity_target')}."
            inc = ""
            if t.get("machine_id"):
                c5, incs = await rest.api_get("/incidents",
                                              params={"machine_id": t["machine_id"], "status": "OPEN"})
                if c5 == 200 and isinstance(incs, list) and incs:
                    inc = f" The machine has {len(incs)} open incident(s)."
            prog = round(float(t.get("progress") or 0) * 100)
            upd = (t.get("updated_at") or "")[:16].replace("T", " ")
            return (f"{_tag(t.get('name'), t.get('id'))} is {t.get('status')}, {prog}% complete. "
                    f"{who} is on it{mac}. Due {t.get('deadline') or 'no deadline'}. "
                    f"Last update {upd or 'unknown'}.{qty}{inc}")

        @function_tool()
        async def get_recent_actions(context: RunContext, limit: int = 5) -> str:
            """What changed lately: recent worker updates and admin decisions.

            Args:
                limit: How many recent actions (1-10).
            """
            try:
                n = max(1, min(10, int(limit)))
            except (TypeError, ValueError):
                n = 5
            seen = []
            for et in ("WORKER_UPDATE", "ADMIN_DECISION"):
                code, data = await rest.api_get("/memory", params={"event_type": et})
                if code == 200 and isinstance(data, list):
                    seen.extend(data)
            if not seen:
                return "No recent actions recorded."
            seen.sort(key=lambda m: m.get("created_at") or "", reverse=True)
            lines = []
            for m in seen[:n]:
                at = (m.get("created_at") or "")[:16].replace("T", " ")
                lines.append(f"{m.get('title', '')} ({at})")
            return "Recently: " + "; ".join(lines)

        @function_tool()
        async def get_plan_status(context: RunContext, plan_ref: str = "") -> str:
            """Overall progress of one work plan: percent, counts, who is behind or blocked.

            Args:
                plan_ref: Plan title, natural reference ("the plan"), or id. Empty lists open plans.
            """
            match, note = await inner._resolve("plan", plan_ref)
            if match is None and note != "fallback":
                if "Which" in (note or ""):
                    return note
                # No ref: list open plans so the model can ask.
                code, data = await rest.api_get("/plans")
                if code != 200 or not isinstance(data, list) or not data:
                    return note or "There are no work plans."
                open_p = [p for p in data if (p.get("status") or "").upper() != "DRAFT"]
                if not open_p:
                    return "All plans are still drafts."
                titles = "; ".join(p.get("title") for p in open_p[:3])
                return f"Which plan: {titles}?"
            pid = match["id"] if match else None
            if pid is None:
                code, data = await rest.api_get("/plans")
                first = (data or [{}])[0] if code == 200 and isinstance(data, list) else {}
                pid = first.get("id")
                if not pid:
                    return "There are no work plans."
            code, prog = await rest.api_get(f"/plans/{pid}/progress")
            if code == 404:
                inner.forget("plan", pid)
                return "That plan no longer exists."
            if code != 200 or not isinstance(prog, dict):
                return "I don't have that information right now."
            p = prog.get("plan", {})
            inner.remember("plan", p.get("id"), p.get("title"))
            counts = p.get("counts", {})
            items = prog.get("items", []) or []
            behind = []
            for it in items:
                if it.get("deleted"):
                    continue
                t = it.get("task") or {}
                if it.get("blocked"):
                    behind.append(f"{t.get('name')} is blocked ({t.get('blocked_reason')})")
                elif it.get("overdue"):
                    behind.append(f"{t.get('name')} is overdue")
            extra = (" " + "; ".join(behind[:2])) if behind else ""
            flags = f" Flags: {', '.join(p.get('flags') or [])}." if p.get("flags") else ""
            return (f"Plan {p.get('title')} is {p.get('status')}, "
                    f"{round(float(p.get('progress') or 0) * 100)}% complete: "
                    f"{counts.get('done', 0)} done, {counts.get('active', 0)} active, "
                    f"{counts.get('pending', 0)} pending.{flags}{extra}")

        @function_tool()
        async def get_worker_progress(context: RunContext, employee_ref: str = "") -> str:
            """How one worker is doing: open vs finished tasks right now.

            Args:
                employee_ref: Employee name, code (EMP-001), id, or "him"/"her". Empty means the recent worker.
            """
            async def legacy():
                code, data = await rest.api_get("/employees")
                if code != 200 or not isinstance(data, list):
                    return None
                want = (employee_ref or "").strip().lower()
                hit = next((e for e in data if want and want in (e.get("name") or "").lower()), None)
                if hit is None:
                    return None
                return {"id": hit["id"], "label": hit.get("name"), "summary": hit.get("name")}
            match, note = await _resolve_or_legacy("employee", employee_ref, legacy)
            if match is None:
                return note or f"I don't have an employee matching {employee_ref}."
            code, tasks = await rest.api_get("/tasks", params={"employee_id": match["id"]})
            rows = tasks if code == 200 and isinstance(tasks, list) else []
            open_t = [t for t in rows if (t.get("status") or "").upper() in ("PENDING", "IN_PROGRESS")]
            done_t = [t for t in rows if (t.get("status") or "").upper() in ("DONE", "COMPLETED")]
            inner.remember("employee", match["id"], match["label"])
            names = "; ".join(t.get("name", "?") for t in open_t[:4])
            extra = f" Working on: {names}." if names else ""
            return (f"{_tag(match['label'], match['id'])} has {len(open_t)} open and "
                    f"{len(done_t)} finished tasks.{extra}")

        # ---- READ coverage for pages (spoken summaries, capped, no ids) ----

        @function_tool()
        async def get_production_summary(context: RunContext) -> str:
            """Production runs at a glance: counts per status and output vs target."""
            code, data = await rest.api_get("/production")
            if code != 200 or not isinstance(data, list) or not data:
                return "There are no production runs."
            counts, target, done = {}, 0, 0
            for r in data:
                st = str(r.get("status") or "PLANNED").upper().replace("_", " ")
                counts[st] = counts.get(st, 0) + 1
                target += int(r.get("quantity_target") or 0)
                done += int(r.get("quantity_completed") or 0)
            parts = ", ".join(f"{n} {st.lower()}" for st, n in sorted(counts.items()))
            pct = round(done * 100 / target) if target else 0
            return (f"{len(data)} production run(s): {parts}. "
                    f"Output {done} of {target} units ({pct}%).")

        @function_tool()
        async def get_iot_status(context: RunContext) -> str:
            """Latest sensor reading per machine and which sensors are stale (no data in 90 seconds)."""
            code, fleet = await rest.api_get("/machines")
            if code != 200 or not isinstance(fleet, list) or not fleet:
                return "I don't have sensor data right now."
            from datetime import datetime, timezone
            stale, fresh, bits = [], 0, []
            for m in fleet[:10]:
                name = m.get("name") or "a machine"
                code2, rows = await rest.api_get(f"/telemetry/{m.get('id')}", params={"limit": 1})
                row = rows[0] if code2 == 200 and isinstance(rows, list) and rows else None
                age = None
                if row:
                    try:
                        dt = datetime.fromisoformat(str(row.get("timestamp") or "").replace("Z", "+00:00"))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        age = (datetime.now(timezone.utc) - dt).total_seconds()
                    except ValueError:
                        age = None
                # Same 90-second staleness rule as the factory map (STALE_MS).
                if age is None or age > 90:
                    when = f"last seen {int(age // 60)} min ago" if age and age > 90 else "stale reading"
                    stale.append(f"{name} ({when})")
                    continue
                fresh += 1
                if len(bits) < 4:
                    bits.append(f"{name} {row.get('temperature')} C, vibration {row.get('vibration')}")
            line = f"{fresh} of {len(fleet)} machine(s) reporting normally."
            if stale:
                line += f" Stale: {'; '.join(stale[:5])}."
            if bits:
                line += f" Latest: {'; '.join(bits)}."
            return line

        @function_tool()
        async def get_reports_summary(context: RunContext) -> str:
            """This week's report: completed/late orders, incidents, decisions, top failing machine."""
            code, d = await rest.api_get("/reports/weekly", params={"week_offset": 0})
            if code != 200 or not isinstance(d, dict):
                return "I don't have the weekly report right now."
            o = d.get("orders") or {}
            inc = d.get("downtime") or {}
            dec = d.get("decisions") or {}
            tops = [t.get("name") for t in (d.get("top_failing_machines") or [])[:3] if t.get("name")]
            bits = [
                f"Week report: {o.get('completed_this_week', 0)} order(s) completed this week, "
                f"{o.get('late_now', 0)} late, {o.get('active_total', 0)} active.",
                f"{inc.get('incidents_raised_this_week', 0)} incident(s) raised, "
                f"{inc.get('currently_open', 0)} open; {dec.get('admin_decisions_this_week', 0)} admin "
                f"decision(s), {dec.get('recommendations_approved', 0)} proposals approved.",
            ]
            if tops:
                bits.append(f"Most incidents: {', '.join(tops)}.")
            return " ".join(bits)

        @function_tool()
        async def get_factory_profile_summary(context: RunContext) -> str:
            """Factory profile summary: industry, machine types, alert limits and autonomy mode. Never credentials."""
            code, prof = await rest.api_get("/profile")
            if code != 200 or not isinstance(prof, dict):
                return "There is no factory profile yet."
            data = prof.get("profile") if isinstance(prof.get("profile"), dict) else {}
            industry = prof.get("industry") or data.get("industry") or "general manufacturing"
            machines = data.get("machines") or []
            types = []
            for m in machines[:12]:
                t = str(m.get("machine_type") or m.get("type") or "other")
                if t not in types:
                    types.append(t)
            thr = data.get("thresholds") or {}
            thr_bits = []
            for tname, ts in list(thr.items())[:4]:
                ts = ts if isinstance(ts, dict) else {}
                thr_bits.append(f"{tname}: {ts.get('temp_max', '?')} C, "
                                f"vibration {ts.get('vibration_max', '?')}, current {ts.get('current_max', '?')} A")
            autonomy = "FAST"
            try:
                c2, a = await rest.api_get("/ai/autonomy")
                if c2 == 200 and isinstance(a, dict) and a.get("autonomy"):
                    autonomy = str(a["autonomy"])
            except Exception:
                pass
            bits = [f"Industry: {industry}. {len(machines)} machine type(s) defined"
                    + (f" ({', '.join(types)})" if types else "") + "."]
            if thr_bits:
                bits.append("Alert limits: " + "; ".join(thr_bits) + ".")
            bits.append(f"AI autonomy mode: {autonomy}.")
            return " ".join(bits)

        @function_tool()
        async def get_users_summary(context: RunContext) -> str:
            """Console accounts by role and active count. Never names, emails or usernames."""
            code, rows = await rest.api_get("/users")
            if code != 200 or not isinstance(rows, list) or not rows:
                return "I don't have the account list right now."
            by_role, active = {}, 0
            for u in rows:
                role = str(u.get("role") or "UNKNOWN").lower()
                by_role[role] = by_role.get(role, 0) + 1
                if u.get("active"):
                    active += 1
            parts = ", ".join(f"{n} {r}" for r, n in sorted(by_role.items()))
            return f"{len(rows)} console account(s): {parts}; {active} active."

        @function_tool()
        async def list_pending_proposals(context: RunContext) -> str:
            """AI proposals waiting for approval on screen (text only, capped)."""
            code, rows = await rest.api_get("/ai/proposals", params={"status": "PENDING"})
            if code != 200 or not isinstance(rows, list) or not rows:
                return "No proposals are waiting for approval."
            heads = [str(p.get("recommendation") or p.get("recommendation_type") or "")[:90]
                     for p in rows[:3]]
            heads = [h for h in heads if h]
            return f"{len(rows)} proposal(s) waiting for approval: " + "; ".join(heads) + "."

        # ---- FAST composite command tools (ONE call, ONE spoken sentence) ----

        async def _command_post(path, body):
            """POST one command and turn the envelope into one spoken line.
            Handles needs_question (ask it once), 409 (clarify), 422 (refusal)."""
            code, data = await rest.api_post(path, body)
            payload = data if isinstance(data, dict) else {}
            if code in _OK:
                nq = payload.get("needs_question")
                if isinstance(nq, dict) and nq.get("question"):
                    opts = [str(o) for o in (nq.get("options") or [])][:3]
                    return (f"{nq['question']} Options: {', '.join(opts)}."
                            if opts else str(nq["question"]))
                created = payload.get("created") or {}
                if created.get("task_id"):
                    inner.remember("task", created["task_id"],
                                   str(body.get("text") or body.get("task_ref") or "task")[:80])
                if created.get("order_id"):
                    inner.remember("order", created["order_id"],
                                   created.get("order_number") or "new order")
                if created.get("proposal_id"):
                    inner.remember("proposal", created["proposal_id"], "pending proposal")
                if payload.get("command_id"):
                    inner.recent_command = payload["command_id"]
                # The backend summary already folds in the warnings.
                return payload.get("summary") or "Done."
            if code in (409, 422):
                d = payload.get("detail") if "detail" in payload else payload
                if isinstance(d, dict):
                    q = str(d.get("question") or "Which one?")
                    opts = [str(o) for o in (d.get("options") or [])][:3]
                    return f"{q} Options: {', '.join(opts)}." if opts else q
                return str(d or "That command can't run.")
            return "I couldn't complete that right now."

        @function_tool()
        async def do_assign_task(context: RunContext, person: str, task_text: str,
                                 order: str = "", machine: str = "",
                                 deadline: str = "", priority: str = "",
                                 autopilot: bool = False) -> str:
            """Create a task AND assign it to a worker NOW, in one call. Use for
            any "assign/create <task> to/for <person>" request. It fills machine,
            skill, deadline and priority itself — never ask about those. Read the
            returned sentence back. person may be "best"/"anyone"/"you decide"
            (it then picks the best qualified worker).

            Args:
                person: Worker name or EMP code, or "best"/"anyone"/"you decide".
                task_text: The task wording, e.g. "CNC operation" or "weld frame".
                order: Optional order number (ORD-001) to link.
                machine: Optional machine code (M-001).
                deadline: Optional natural deadline ("by Friday", "tonight").
                priority: Optional LOW/NORMAL/HIGH/URGENT.
                autopilot: True when the admin said "you decide"/"just do it".
            """
            pill = (person or "").strip()
            low = pill.lower()
            text = (task_text or "").strip() or pill or "task"
            body = {"text": text, "source": "voice", "autopilot": bool(autopilot)}
            if pill and (low.startswith(("best", "anyone", "anybody", "you decide", "yourself"))
                         or low in ("best", "anyone", "anybody", "you decide", "yourself")):
                # Keep the word (e.g. "welder") so the skill matcher sees it.
                body["text"] = f"{text} {pill}"
            elif pill:
                body["employee_ref"] = pill
            if order:
                body["order_ref"] = order
            if machine:
                body["machine_ref"] = machine
            if deadline:
                body["deadline_text"] = deadline
            if priority:
                body["priority"] = priority
            return await _command_post("/ai/commands/task", body)

        @function_tool()
        async def do_create_order(context: RunContext, product: str,
                                  quantity: int = 0, customer: str = "",
                                  autopilot: bool = False) -> str:
            """Create a customer order NOW, in one call; read the sentence back.
            Use for "create an order for 50 gear housings for Acme". Never ask to
            confirm; quantity and customer may be omitted.

            Args:
                product: What the order is for, e.g. "gear housings".
                quantity: How many units (0 if not said).
                customer: Customer name if given.
                autopilot: True when the admin said "you decide"/"just do it".
            """
            body = {"product": product or "General", "quantity": int(quantity or 0),
                    "autopilot": bool(autopilot), "source": "voice"}
            if customer:
                body["customer"] = customer
            return await _command_post("/ai/commands/order", body)

        @function_tool()
        async def do_change_task(context: RunContext, task_ref: str = "",
                                 worker: str = "", machine: str = "",
                                 deadline: str = "", priority: str = "",
                                 status: str = "", autopilot: bool = False) -> str:
            """Change an existing task NOW, in one call: reassign, move machine,
            change deadline or priority, or mark started/completed. Use for
            "move that task to Friday", "make it urgent", "mark it complete",
            "reassign it to Ravi". Read the sentence back. NEVER use this (or any
            tool) to delete a task — refuse and name the Tasks screen instead.

            Args:
                task_ref: Task name, code phrase, or "that task".
                worker: New worker name/EMP code (optional).
                machine: New machine code (optional).
                deadline: Natural deadline, e.g. "Friday" (optional).
                priority: LOW/NORMAL/HIGH/URGENT (optional).
                status: "started" or "completed" (optional).
                autopilot: True when the admin said "you decide"/"just do it".
            """
            body = {"task_ref": task_ref or "", "source": "voice",
                    "autopilot": bool(autopilot),
                    "text": " ".join(x for x in (task_ref, status) if x)}
            if worker:
                body["employee_ref"] = worker
            if machine:
                body["machine_ref"] = machine
            if deadline:
                body["deadline_text"] = deadline
            if priority:
                body["priority"] = priority
            if status:
                body["status"] = status
            return await _command_post("/ai/commands/change", body)

        @function_tool()
        async def undo_last(context: RunContext) -> str:
            """Undo the most recent command: delete what it created, or restore
            previous values. Use for "undo that", "cancel that", "revert that".
            Read the sentence back. Fails if more than 15 minutes passed or the
            work was already started.
            """
            code, data = await rest.api_post("/ai/commands/undo-last", {})
            payload = data if isinstance(data, dict) else {}
            if code in _OK:
                return payload.get("summary") or "Undone."
            if code == 404:
                return "There is nothing recent to undo."
            if code == 409:
                d = payload.get("detail") if "detail" in payload else payload
                return f"I can't undo that: {d}"
            return "I couldn't undo that right now."

        @function_tool()
        async def navigate_ui(context: RunContext, action: str = "navigate",
                              page: str = "", machine: str = "", order: str = "",
                              incident: str = "", filter: str = "") -> str:
            """Show something on the admin screen: open a page or focus an entity.
            Never claims data changed. Answers in ONE short sentence.

            Args:
                action: navigate (open a page), select_machine, open_order, open_incident, focus_order_on_map, show_proposals.
                page: Page in ANY natural form for navigate: "the Machines tab", "production", "progress tracker".
                machine: Machine code/name for select_machine.
                order: Order number for open_order/focus_order_on_map.
                incident: Incident id, or machine code like M-001, for open_incident.
                filter: Optional preset the page's UI already has ("open", "overdue", "live").
            """
            import json as _json
            allowed = {"navigate", "select_machine", "open_order", "open_incident",
                       "focus_order_on_map", "show_proposals"}
            if action not in allowed:
                return f"Unknown screen action {action}."
            payload = {"action": action}
            # One short sentence the model reads back verbatim.
            speak = None
            if action == "navigate":
                if not (page or "").strip():
                    return "Which page? I can open: " + ", ".join(nav.page_labels()[:3]) + "."
                resolved = nav.resolve_page(page)
                if resolved is None:
                    return nav.unknown_page_message(page)
                page_id, label, alias_filter = resolved
                filt_key = None
                if (filter or "").strip():
                    filt_key = nav.resolve_filter(page_id, filter)
                    if filt_key is None:
                        opts = ", ".join(nav.filter_speak_list(page_id)) or "none"
                        return f"I can't filter {label} that way; I can show: {opts}."
                elif alias_filter:
                    filt_key = alias_filter
                payload["page"] = page_id
                if filt_key:
                    payload["filter"] = filt_key
                    speak = f"Opening {label}: {nav.filter_speak(page_id, filt_key)}."
                else:
                    speak = f"Opening {label}."
                inner.remember("page", page_id, label)
            else:
                # Only the one field this action allows (the browser
                # validator rejects anything else as strict).
                field = {"select_machine": "machine", "open_order": "order",
                         "open_incident": "incident",
                         "focus_order_on_map": "order"}.get(action)
                value = {"select_machine": machine, "open_order": order,
                         "open_incident": incident,
                         "focus_order_on_map": order}.get(action)
                if field and value:
                    payload[field] = value
                target_page = {"select_machine": "machines", "open_order": "orders",
                               "open_incident": "incidents", "focus_order_on_map": "map",
                               "show_proposals": "ai"}.get(action)
                if target_page:
                    speak = f"Opening {nav.label_of(target_page)}."
                    inner.remember("page", target_page, nav.label_of(target_page))
            room = self._room_getter()
            if room is None:
                return "No live room. The screen could not be updated."
            target = await inner._find_browser_target()
            if not target:
                return "No admin browser in the room. The screen could not be updated."
            try:
                resp = await room.local_participant.perform_rpc(
                    destination_identity=target,
                    method="ui.command",
                    payload=_json.dumps(payload),
                    response_timeout=inner.RPC_TIMEOUT_S,
                )
            except Exception as e:
                import logging as _logging
                _logging.getLogger("jarvis.voice").warning(
                    "ui.command RPC failed: %s", type(e).__name__)
                msg = str(e)[:150]
                if "timeout" in msg.lower() or "timed out" in msg.lower():
                    return "The screen took too long to answer. Please say it again."
                return "The screen could not be updated. Please try again."
            text = str(resp or "")
            if text.startswith("ok"):
                return speak or "Shown on the admin screen."
            if "handler reloading, please retry" in text:
                # Browser mid-remount (stale RPC closure): one quick retry
                # heals the turn instead of speaking a technical error.
                import asyncio as _asyncio
                import logging as _logging
                _logging.getLogger("jarvis.voice").warning("ui.command stale handler, retrying once")
                try:
                    await _asyncio.sleep(0.6)
                    resp2 = await room.local_participant.perform_rpc(
                        destination_identity=target,
                        method="ui.command",
                        payload=_json.dumps(payload),
                        response_timeout=inner.RPC_TIMEOUT_S,
                    )
                except Exception as e2:
                    _logging.getLogger("jarvis.voice").warning(
                        "ui.command retry failed: %s", type(e2).__name__)
                    return "The screen took too long to answer. Please say it again."
                text = str(resp2 or "")
                if text.startswith("ok"):
                    return speak or "Shown on the admin screen."
            # The browser returns a speakable refusal; drop the machine prefix.
            return text.replace("rejected: ", "", 1)[:200]

        @function_tool()
        async def end_session(context: RunContext) -> str:
            """End the voice session, ONLY on an explicit user request
            ("end session", "stop listening", "disconnect", "goodbye Jarvis").
            Says one closing line, then signals the browser to run its normal
            End flow (delayed, so the goodbye is heard). Never call this for
            navigation or any other request.
            """
            import json as _json
            room = self._room_getter()
            if room is not None:
                target = await inner._find_browser_target()
                if target:
                    try:
                        await room.local_participant.perform_rpc(
                            destination_identity=target,
                            method="voice.end_session",
                            payload=_json.dumps({}),
                            response_timeout=inner.RPC_TIMEOUT_S,
                        )
                    except Exception:
                        pass
            return "Okay, ending the session."

        return [get_factory_overview, list_machines_needing_attention,
                get_machine_status, get_order_status, list_open_incidents,
                analyze_incident, list_available_employees, get_employee_workload,
                list_unassigned_tasks, suggest_assignment, propose_assignment,
                propose_maintenance, propose_delay, navigate_ui,
                get_task_status, get_recent_actions, get_plan_status,
                get_worker_progress,
                get_production_summary, get_iot_status, get_reports_summary,
                get_factory_profile_summary, get_users_summary,
                list_pending_proposals,
                do_assign_task, do_create_order, do_change_task, undo_last,
                end_session]
