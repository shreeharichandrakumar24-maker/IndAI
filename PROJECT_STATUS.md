# IndAI — Build Log & Roadmap
**Updated:** 3 Oct 2026 | **Stack:** FastAPI + Supabase Postgres · React + Vite · Flutter (Android) · LiveKit voice
**Repo:** `D:\IET project\IndAI` (Windows/PowerShell — quote paths, they contain a SPACE)

## 0. How to work in this repo (for the next AI session)
- **Modes matter:** plan mode = read-only (inspect, answer, never edit/run writes); build mode = may edit, run, verify.
- **Safety rules (standing):** no DB drops/resets; additive migrations only (`backend/db/migrations/`, `IF NOT EXISTS`); M-001…M-008 + 15 seeded workers never deleted; never print/log/commit secrets (`.env`, `.env.local`, tokens, keys); `git status` must show no `.env*`/venv/credentials before finishing; do not commit unless asked.
- **LLM gateway:** ALL model calls go through `backend/services/llm.py::complete_json` (JSON mode w/ plain-text fallback retry for providers like Groq gpt-oss that reject `response_format`; validates against Pydantic models; raises `LLMUnavailable`). Never fake AI output — 503 + labeled deterministic fallback instead.
- **Approval rule:** AI proposes (PENDING), human approves via clicks. No silent writes, no auto-execute anywhere (voice included).
- **Dev bypass (testing only):** `AUTH_DISABLED=true` in `backend/.env` + `VITE_AUTH_DISABLED=true` in `frontend/.env` skips login (dev MANAGER). `DEV_VIEW_AS=<worker name>` scopes mobile `/mine`. Flip both to `false` + real Auth accounts for anything production-like.
- **Run:** `.\start-backend.ps1` (:8000, kills squatters), `.\start-all.ps1` (backend+website+simulator, opens voice window only if LiveKit keys exist), `.\stop-all.ps1`, `.\start-voice.ps1` (Jarvis agent, refuses cleanly without keys). All ASCII-only, `Split-Path`-rooted, 0 parse errors.
- **Verify pattern:** backend `python -m py_compile`; frontend `npm run build` + `npm run lint` (0 errors; warnings are the established set-state-in-effect pattern); live checks via API + headless Chrome (`npx -p playwright-core`, system Chrome, fake-media flags); temp scripts live OUTSIDE the repo (`.../Temp/opencode/`); clean up all temp data (residue queries must return 0).

## 1. Original track — self-configuring factory (Phases A–E), DONE live-verified
- **A Foundation:** `services/llm.py`, CNC preset (M-001…M-008), `factory_profile` table + `/api/profile` (generate→review→approve→idempotent seed).
- **B Onboarding:** 6 questions → editable AI/Preset review → approve; Factory Profile page; skip-with-preset.
- **C Import:** `/api/import/analyze|commit`, AI mapping + rule-based fallback, coercion, validation, dedup, per-row errors; `docs/sample_data/`.
- **D Detection:** profile thresholds w/ defaults fallback, ingest auto-detection in try/except, incident enrichment (task/order/employee), dedup preserved.
- **E Analysis+memory:** incident snapshot, deterministic order risk, `POST /ai/analyze-incident`, Approve/Reject → `factory_memory` (+PENDING maintenance only for approved SCHEDULE_MAINTENANCE), 409 on re-decide, `GET /api/memory`, 503 without key.

## 2. Boss-ready track (Phases 1–7), DONE
1. **Login+roles** (Supabase Auth, `app_users`, first login = MANAGER, Users page, role nav, worker mobile-only screen, one-file auth middleware). **Currently bypassed by dev flags (see §0).**
2. **Boss dashboard + notifications** (Boss/Admin toggle, plain verdicts, 🔔 bell; triggers: incident / HIGH risk / approvals).
3. **Tasks page** (CRUD, filters, ▶/✓ advance, status validation).
4. **Simulator merged** (in-app manager Simulator page; standalone `:5174` reference-only).
5. **Reports** (`GET /api/reports/weekly`, week picker, CSV, print CSS).
6. **AI Assistant chat** (`POST /ai/chat`, 2 executable kinds, invented IDs dropped).
7. **Plans → worker mobile** (`work_plans`/`plan_assignments`/`fcm_tokens`, approve→dispatch matcher, idempotent; Flutter app; APK installed on Infinix via USB + `adb reverse` tunnel).

## 3. Third layer — Features 6–10 (your part), DONE
- **F6 AI assignment:** `POST /plans/{id}/suggest` (candidates → LLM rank → invented-ID drop; labeled deterministic fallback), `PATCH /assignments/{id}/pair` (manager-only), Plans console (draft/approve/suggest/apply/dispatch).
- **F7 Cross-system root cause:** `POST /ai/root-cause` (6-system join, evidence + validated IDs) + Deep-analysis panels on Machine/Order details.
- **F8 Predictive order risk:** `GET /orders/at-risk` (+AI delay estimates), notify endpoint, live boss-view list.
- **F9 What-if simulation:** `POST /ai/simulate` (DELAY/RESOLVE/REASSIGN projectors, display-only, apply via normal endpoints), Simulate page.
- **F10 Organizational memory:** `POST /memory/log`, `GET /memory/search|/similar`, dispatch/resolve/apply auto-writes, search chips + similar-events sidebars.

## 4. Voice (all three generations — know which is which)
- **V1 browser speech** (Assistant page): mic button (Web Speech STT) + spoken replies (speechSynthesis) + voice picker (persisted) + push-to-talk/hold + repeat-back review + echo guard (drops own-speaker feedback) + record/stop button. `services/voice.js` shared lib.
- **V2 Jarvis realtime tab** (`pages/Jarvis.jsx`, nav `Jarvis`): tap-to-start + continuous listen, **wake word is just `jarvis`** (10 s cooldown), fast brain (`LLM_MODEL_VOICE`, default `openai/gpt-oss-20b`), SSE sentence streaming (`POST /ai/assistant/voice`, max 2 tool turns), progressive speech queue, **barge-in** with echo guard, orb states, transcript, chips, approval cards, floating mic hidden on this route.
- **V3 LiveKit agent** (`Jarvis/`, agent_name `indai-voice`): `POST /api/voice/token` (fresh room, 10-min TTL, explicit dispatch; 503 without `LIVEKIT_*`), 14 REST-only tools (`src/tools.py`, no DB creds), `navigate_ui` → browser RPC `ui.command` (strict validator `components/voice/uiCommand.js`, 12/12 unit-tested). VoicePanel (floating mic, shell-level, crash-fixed) + status checklist. **Requires LiveKit Cloud keys** (`Jarvis/.env.local` + `backend/.env`); `src/test_join.py` proves join (exit 0 = agent in room).
- LiveKit Inference models: LLM `openai/gpt-oss-120b`, **TTS `cartesia/sonic-turbo`** (required arg — job crashed without it, fixed), STT/VAD/TurnDetector defaults.

## 5. Mobile-app track (mobile-only prompts), DONE
- **Factory Map:** floor-plan SVG (zones, type icons, status colors, stale-grey, red pulse), side panel, search/filter/Order-focus, drag-edit + save/reset via profile `layout` JSON, `navigate(route, payload)` cross-page links, focus props on Machines/Orders/IoT/Incidents.
- **Tasks monitoring upgrade:** 6 KPIs incl. overdue, machine/order filters, progress bars, linked run + same-machine incidents + Open-order in details, create removed (stays in Orders→Split).
- **Smart Split:** `services/smart_split.py` + `POST /ai/smart-split` (candidates + LLM pick, invalid IDs dropped/cleared, rule fallback), editable proposal table, sequential approve-creates; Manual Split untouched.
- **Jarvis assistant (tool-loop):** `services/assistant.py` (9 read tools) + `/ai/assistant/*` (bounded 4-turn loop, proposals PENDING with `params` JSONB via migration `005`, decision executes SCHEDULE/REASSIGN/DELAY + always writes memory, 409 repeat). Replaced old chat UI wholesale.

## 6. Database (16 → 17 tables, all additive, nothing dropped)
`schema.sql` (10) → `001_factory_profile` → `002_app_users` → `003_notifications` → `004_work_plans` → `005_ai_recommendation_params` (`params` JSONB) → `006_worker_credentials` (scrypt-hashed prototype logins). Project `qxhwsuzzdwjmpfdqwwri` (ap-south-1); Session-pooler URI; RLS OFF (dev); 8 machines + 15 seeded workers intact.
- **Thresholds (per type, Task 1 fix):** CNC 85/5/10/**1100**, Press **70**/5/**18**/**0**, Grinder **80**/5/10/**2500**, Welder **90**/5/**22**/**0**, Robot 85/5/10/**800**, Laser 85/5/**13**/**0**, Molder **100**/5/**16**/**600**, _default 85/5/10/1300. Proven by `backend/tests/test_thresholds.py` (3 tests: 8 baselines clean, 8 abnormals trip, reference spike). Reset button on Factory Profile page backfills approved profiles without re-onboarding.
- **Demo tooling:** `backend/scripts/{demo_scene (setup/trigger/reset, HTTP-only), preflight (PASS/FAIL/WARN + READY verdict), rehearse (12/12 PASS), seed_employees}`; `docs/{DEMO_RUNBOOK,PITCH_NOTES,VOICE_AGENT}.md`.

## 7. Bugs found & fixed (don't reintroduce)
VoicePanel null-creds crash · memory 500 (`serialization_alias`) · approve `seed` dropped · skills parser `{"items": []}` fallthrough · skills rewrite keeps dict/list/string tolerance · Kotlin `kotlin.incremental=false` · TTS model required · httpx base-path double-`/api` in scripts · PowerShell quote-mangling (use temp script files) · no-op edit tool calls that merged lines (always re-read after edits) · `.env` stale-cache (restart backend after changes).

## 8. Still pending (needs human)
- Supabase Auth account for click-through proof (dev bypass covers testing).
- Firebase project for real push (bell fallback works); iOS build; `google-services.json` never in repo.
- LiveKit Cloud keys live in both `.env` files now — rotate them if chat history is ever shared.
- `LLM_API_KEY` = Groq key in `backend/.env` (gitignored); gateway auto-falls-back when providers reject JSON mode.
- Real microphone/audio verification and phone tap-through after every voice/mobile change.

## 9. PART 5 — agent line + auth passthrough + verification + cleanup (verified 4 Oct 2026)
- **Agent line:** `Jarvis/src/agent.py` `INSTRUCTIONS` gained one sentence (old weaker sentence kept): "Never reveal or read out passwords, password hashes, tokens, login credentials, employee emails or login usernames; if asked, say you cannot share login details and that the admin can create or reset a worker login on the Employees page." No Jarvis tools added/removed/changed.
- **Auth passthrough (prototype worker login, additive only):** `AuthMiddleware` lets exactly `POST /api/worker-auth/login` through as public, and every route starting with `/api/worker/` (trailing slash) plus `POST /api/worker-auth/change-password` skips the Supabase check so `get_current_worker` (own HMAC Bearer token) is the sole gate. `AUTH_DISABLED` behavior and every admin endpoint untouched. Guard test `backend/tests/test_worker_auth_passthrough.py` (4 tests) enumerates all 9 `/worker/*` routes + change-password from the routers and asserts each is 401 without a worker token; only login is public.
- **Verified:** unittest 14/14 PASS (thresholds + skills + passthrough); live API 8/8 (health open, login public with worker-401, all `/worker/*` + change-password worker-401, admin gating unchanged); preflight worker login round-trip HTTP 200 (new 6-col-tolerant parser); `py_compile` clean; frontend `npm run build` PASS + `lint` 0 errors (established warnings only); `flutter analyze` no issues; Jarvis agent compiles, tools list unchanged. No claims about real phone taps or live LiveKit audio (not tested).
- **Cleanup (scoped only):** fixed stale `worker_auth.py` docstring (HMAC tokens, still labeled prototype); rewrote stale `mobile_app/README.md` endpoint section to the real `/api/worker/*` routes; `preflight.py` parses both 6-col and 4-col creds files (uses `identifier`); `seed_employees` and `backfill_worker_auth` share `backend/scripts/cred_file.py` merge helper — safe in any order (codes/emails never renumbered, existing hashes untouched), creds file is merge/append-only with `.bak` backup first (`docs/demo_worker_credentials.txt.bak` gitignored). `push.dart` unwired as before, admin N+1 untouched, no refresh/revoke (12 h non-revocable prototype token stays).
