# IndAI Pitch Notes (6 Oct 2026)

## Problem statement

Small mechanical factories run on registers, Excel sheets, and the
supervisor's memory. Breakdowns are discovered late, orders slip without
warning, and nobody can answer "which orders are at risk right now?" The
tribal knowledge of what broke, what fixed it, and who is good at what
walks out the door every evening.

## Architecture (describe this diagram)

```
Simulator / ESP32 sensors --telemetry--> FastAPI --stores--> Supabase Postgres
                                              |
                                    Abnormality Engine (deterministic)
                                              |
                                     Incident -> Maintenance workflow
                                              |
                                       Factory Context snapshot
                                              |
                        AI Assistant (Groq LLM, JSON-validated, labeled AI)
                                              |
                        Admin chat + approvals -> Factory Memory (the story)
                                              |
                        Plans -> dispatch -> Flutter worker app (jobs, proof)
                                              |
                        LiveKit voice agent (Jarvis/) -> proposes, never applies
```

Deterministic core, AI advisory layer, human approval on every change.

## 10 features and where each is visible

1. **Onboarding wizard + factory profile** - first-run setup; Factory Profile
   page (machines, thresholds, templates, skills).
2. **Excel/CSV import with AI column mapping** - Import page (mapping table,
   confidence, preview, result counts).
3. **Live detection + incident enrichment** - IoT Monitoring + Incidents
   (auto-created, linked order/task, deduped, severity).
4. **AI analysis + admin decisions + memory** - Incident "Analyze with AI":
   root cause, order risk, Approve/Reject cards, Factory Memory timeline.
5. **Login + roles** - Users page (dev bypass ON for the demo; production
   uses Supabase Auth).
6. **Boss dashboard + notifications** - Dashboard Boss view (plain verdicts),
   bell with incident/risk/approval alerts.
7. **Work plans + dispatch + worker mobile app** - Plans page
   (draft/approve/suggest/apply/dispatch) -> phone shows the job.
8. **Reports + What-If simulation** - Reports page (CSV/print); What-If page
   (display-only projections, apply-through-normal-pages).
9. **AI Assistant chat + Jarvis voice tab** - AI Assistant (tool loop, traces,
   approval cards); Jarvis (realtime voice, "jarvis" wake, barge-in).
10. **Organizational memory** - Factory Memory page (search, event chips,
    similar-events on incident/machine pages); every approval writes history.

## Self-configuring onboarding story (60 seconds)

New factory opens IndAI -> answers 6 questions -> AI drafts machines,
sensors, alert limits, task steps, skills -> admin edits and approves ->
existing Excel/CSV uploaded -> AI maps messy columns to tables -> data
imported -> live telemetry flows.-defaults cover a CNC/mechanical shop.

## Honest limits (say these before judges ask)

- Worker login is a **prototype** (username/password, no tokens).
- Sensors are **simulated** (web simulator + scripted payloads).
- AI needs an LLM key; without it every AI surface degrades to labeled
  deterministic output (never fake AI).
- Voice needs LiveKit Cloud keys; mobile push needs Firebase.
- Auth wall is OFF for the demo (dev bypass); RLS is off (dev database).

## Hardware slide: ESP32 gateway (future, not built)

Suggested sensors per measurement:

| Measurement | Sensor | Notes |
|---|---|---|
| Temperature | DS18B20 (digital, waterproof) or MAX6675 + K-type thermocouple | One per spindle/motor |
| Vibration | ADXL345 / MPU-6050 accelerometer | RMS vibration maps to the 5.0 limit |
| Current | ACS712 Hall-effect (5/20/30 A variants) | Per-machine supply line |
| RPM | IR reflective sensor (LM393) or Hall + magnet | Pulses per revolution |

MQTT topic layout (gateway publishes, bridge POSTs to the API):

```
indai/<factory>/<machine_code>/telemetry
{"machine_code": "M-001", "temperature": 68.5, "vibration": 2.1,
 "current": 8.2, "rpm": 1450, "machine_status": "RUNNING", "ts": "<iso>"}
```

The bridge maps `machine_code` to `machine_id` and POSTs
`/api/telemetry` unchanged — detection, incidents, and AI all work
identically on real hardware data.

## Future work

Real auth (Supabase Auth + RLS), FCM push, MQTT/OPC-UA bridge service,
photo/voice problem reports from the phone, multi-factory scoping,
policy-based auto-approval, iOS build.
