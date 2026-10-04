# IndAI Demo Runbook (final demo, 6 Oct 2026)

All commands run from "D:\IET project\IndAI" (quote the path - it contains
a SPACE). Backend :8000, admin frontend :5173, simulator :5174.

## 1. Start order

```powershell
cd "D:\IET project\IndAI"
.\start-backend.ps1      # FastAPI :8000 (kills port squatters itself)
# new window:
cd "D:\IET project\IndAI\frontend"; npm run dev     # :5173
# new window (demo telemetry source):
cd "D:\IET project\IndAI\iot_simulator\frontend"; npm run dev   # :5174
# new window, only for the voice part (needs Jarvis/.env.local, see below):
.\start-voice.ps1        # Jarvis agent; refuses cleanly if keys missing
# phone (optional): USB + adb reverse tcp:8000 tcp:8000, open IndAI worker
```

## 2. Preflight (must say READY)

```powershell
cd "D:\IET project\IndAI"
python -m backend.scripts.preflight
```

Fix FAILs before presenting: start missing services; run
`python -m backend.scripts.demo_scene reset` on DEMO leftovers; stray OPEN
incidents are a WARN (resolve them in Incidents if you want a green map).

## 3. Prepare the scene

```powershell
python -m backend.scripts.demo_scene setup     # idempotent, safe to repeat
```

Creates DEMO-1/2/3 orders, 9 tasks (3 UNASSIGNED), 3 runs, NORMAL readings.

## 4. Live demo script (~5 minutes)

1. **Admin order (30 s):** Orders page, show DEMO-2 (tight deadline).
2. **Smart split (45 s):** open DEMO-2 -> Smart Split tab -> Generate
   (AI or rule-based badge) -> Approve 1-2 tasks -> they appear in Tasks.
3. **Voice/AI assignment (60 s):** Jarvis tab or AI Assistant:
   "assign the unassigned laser job to the best person" -> proposal card ->
   **Approve** -> task assigned. Or Plans page AI-suggest + Apply + Dispatch.
4. **Phone (30 s):** worker app pull-to-refresh -> job appears -> Accept.
5. **Set Abnormal on M-001 (30 s):** simulator page -> map node turns red,
   bell rings, incident opens (linked order/task shown).
6. **AI root cause + order risk (45 s):** incident -> Analyze with AI ->
   root cause, deterministic risk, recommendations -> **Approve** one ->
   maintenance row + Factory Memory entry.
7. **Worker report (30 s):** phone app -> task -> Report a problem ->
   incident appears in admin Incidents with `[Worker report]` prefix.
8. **Close (15 s):** memory timeline shows the story; resolve + reset.

## 5. Recovery tips (when things fail live)

- **LLM down/429:** every AI surface degrades to labeled deterministic output
  (rule-based badges, 503 with clear message). Demo the deterministic path.
- **LiveKit/voice down:** `POST /api/voice/token` 503 is by design; use the
  AI Assistant page (same tools, text) and quick-stats buttons.
- **Wi-Fi dead:** `adb reverse tcp:8000 tcp:8000` + phone app on
  `http://127.0.0.1:8000`; backend/frontend are localhost-only anyway.
- **Simulator silent:** `python -m backend.scripts.demo_scene trigger --machine M-001`
  posts the abnormal payload directly (same detection path).
- **Stale red map:** resolve stray OPEN incidents first (preflight WARNs).

## 6. Reset for a clean second run

```powershell
python -m backend.scripts.demo_scene reset
```

Removes DEMO- orders (cascades tasks/runs), demo incidents/maintenance,
rejects demo PENDING proposals, posts NORMAL readings. Keeps (by design):
rejected-proposal history, telemetry history, factory_memory story rows.
Verify: `python -m backend.scripts.preflight` (DEMO check back to PASS).
