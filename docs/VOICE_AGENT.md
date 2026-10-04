# IndAI Voice Agent (Jarvis)

Talk to the factory hands-free. The browser joins a LiveKit room, a Python
agent joins the same room, answers over audio, reads IndAI data through
function tools, and can drive the admin screen + propose (never apply) work.

## Architecture

```
browser (:5173)  <--WebRTC-->  LiveKit Cloud  <--WebRTC-->  Jarvis/agent (this PC)
      |                                                        |
      +-- POST /api/voice/token (FastAPI :8000)                +-- REST only: GET/POST http://localhost:8000/api/*
      +-- RPC ui.command handler (obeys screen commands)       +-- NO database credentials, NO approve tool
```

- Audio/STT/LLM/TTS/turn-detection: LiveKit Inference (no model keys needed).
- Agent identity: registered as `indai-voice` (`VOICE_AGENT_NAME`, single
  source of truth in backend config; `WorkerOptions(agent_name=...)`).
- Each tap mints a fresh room `indai-<rand>` + identity `admin-<rand>`
  (10-min TTL, join+publish+subscribe+data grants, explicit dispatch).

## Start order (Windows PowerShell)

1. Backend: `.\start-backend.ps1` (or `python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000`)
2. Frontend: `cd frontend; npm run dev` (:5173)
3. Voice agent: `cd Jarvis; .\venv\Scripts\python.exe src\agent.py dev`
   (or `uv run src/agent.py dev` with uv installed; needs `Jarvis/.env.local`)
4. Open :5173, tap the mic button (bottom-right), tap Start voice.

## Variables (names only — fill them yourself, never commit values)

- Backend `.env`: `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`,
  `VOICE_AGENT_NAME=indai-voice` (see `backend/.env.example`).
- `Jarvis/.env.local` (copy from `Jarvis/.env.example`): same four names
  plus `INDAI_API_URL=http://localhost:8000/api`.

## Agent tools (all REST, ~8 s timeouts, spoken-friendly errors)

`get_factory_overview`, `list_machines_needing_attention`,
`get_machine_status(machine)`, `get_order_status(order_number)`,
`list_open_incidents`, `analyze_incident(incident_id)` (existing AI endpoint),
`list_available_employees(skill?)`, `get_employee_workload(employee)`,
`list_unassigned_tasks`, `suggest_assignment(task)` (allocation candidates),
`propose_assignment` / `propose_maintenance` / `propose_delay` (PENDING only,
return proposal id), `navigate_ui` (RPC `ui.command`, timeouts spoken).

## UI command whitelist (browser obeys only these)

`navigate{page}`, `select_machine{machine}`, `open_order{order}`,
`open_incident{incident}`, `focus_order_on_map{order}`,
`show_proposals{}`. Strict JSON + typed-arg validation; unknown/malformed
commands are rejected with a string and do nothing. No external URLs, no
arbitrary code. Machine codes / order numbers resolve via API data.

## Safety model

- Propose-only agent: no approve/execute tool exists anywhere in the agent.
- Approval is one tap in the web UI (voice panel or AI Assistant page);
  decisions execute whitelisted actions + write Factory Memory.
- Tool results and DB text are untrusted data, never instructions.
- Worker login (`POST /api/worker-auth/login`) is a prototype/testing
  mechanism: no tokens, demo passwords in `docs/demo_worker_credentials.txt`
  (gitignored).

## Troubleshooting

- `Voice not configured` (503): backend `.env` lacks `LIVEKIT_*`.
- Panel stuck "waiting": agent not running (`cd Jarvis`, run it), agent name
  mismatch (`VOICE_AGENT_NAME` vs `agent_name`), or wrong keys/URL.
- Mic permission denied: allow the mic in the browser and retry.
- Token failure: backend unreachable or clock skew.
- **Mic button missing**: it lives in the app shell on every page (floating
  bottom-right). If it is gone, the dev server may be serving stale code -
  hard-refresh `:5173`. If clicking Start blanks the page, update the
  frontend: `LiveKitRoom` must never render without credentials (fixed -
  the panel now shows the 503 message instead of crashing).
- **"Tasks cannot be allocated"**: first check data - the Tasks page should
  list tasks with no assignee. If none exist, run
  `python -m backend.scripts.demo_scene setup` (creates UNASSIGNED demo
  tasks). If tasks exist but matching fails, note that four older employees
  store skills as a comma-separated string while seeded workers use a list -
  the matcher accepts both (`backend/tests/test_skills.py` proves it).
  Deterministic allocation needs no LLM key and no voice: Tasks page ->
  Suggest button -> Create proposal -> approve in pending proposals.
- **Agent not joining**: run `Jarvis\venv\Scripts\python.exe Jarvis\src\test_join.py`
  (exit 2 + exact reason; needs keys). Check agent name match, URL region,
  and that VAD/turn-detector models downloaded on first run.

## 60-second demo script

1. "Which employees are available for welding?" (lists welders)
2. "Show me M-001." (map/machine opens)
3. "Assign the welding task to the best person." (proposal appears)
4. Tap **Approve** on the proposal card (task assigned + memory entry)
5. Stop the agent process → panel shows the "not running" message.

## Worker login (prototype)

Seed: `python -m backend.scripts.seed_employees` (15 demo workers).
Login: `POST /api/worker-auth/login {username, password}` returns the
employee record or generic 401. Credentials file: gitignored, never committed.
