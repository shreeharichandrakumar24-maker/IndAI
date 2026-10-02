# IndAI — Build Log & Roadmap
**Date:** 30 Sep 2026 | **Stack:** FastAPI + Supabase Postgres · React + Vite · Flutter (Android)

## 1. What was built today

### 1A. Self-configuring factory (original track, Phases A–E) — DONE, live-verified
- **A: Foundation** — `services/llm.py` (sole LLM gateway, JSON-mode, 1 retry, typed `LLMUnavailable`), CNC preset (M-001…M-008 + 85/5/10/1300 limits), `factory_profile` table + `/api/profile` (generate → review → approve → idempotent seed).
- **B: Onboarding wizard** — 6 questions → editable AI/Preset review → approve; Factory Profile page; "Skip — use CNC preset".
- **C: Excel/CSV import** — `/api/import/analyze|commit`, AI mapping with rule-based fallback, type coercion, Create-schema validation, dedup, per-row errors; sample files in `docs/sample_data/`.
- **D: Live detection** — profile thresholds (defaults fallback), ingest auto-detection in try/except, incident enrichment (task/order/employee when unambiguous), dedup preserved.
- **E: AI analysis + memory** — incident context snapshot, deterministic order risk, `POST /ai/analyze-incident`, Approve/Reject → `factory_memory` (+PENDING maintenance only for approved SCHEDULE_MAINTENANCE), 409 on re-decide, `GET /api/memory`, graceful 503 without key.

### 1B. Boss-ready track (Phases 1–7) — DONE (code), click-proof pending one account
1. **Login + roles** — Supabase Auth, `app_users`, first login = MANAGER, Users page, role-filtered nav, worker mobile-only screen, one-file auth middleware (open: health + simulator ingest).
2. **Boss dashboard + notifications** — Boss/Admin toggle, plain-language verdicts, bell (`notifications` table, triggers: incident / HIGH order-risk / approvals).
3. **Tasks page** — full CRUD, filters, Start / Done one-click advance, status validation.
4. **Simulator merged** — in-app manager-gated Simulator page (seed + 10s loop + Abnormal pins); standalone `:5174` retired to reference-only.
5. **Reports** — `GET /api/reports/weekly`, Reports page (week picker, CSV, print stylesheet).
6. **AI Assistant chat** — `POST /ai/chat` over read-only context, 2 executable kinds only (Apply-gated), invented IDs dropped.
7. **Plans → worker mobile** — `work_plans`/`plan_assignments`/`fcm_tokens`, approve→dispatch engine (skill/availability/machine match, idempotent), worker endpoints, Flutter Android app (`mobile_app/`, `flutter analyze` clean) — **APK built & installed on Infinix via USB**.

### 1C. Bugs found & fixed during verification
- Approve response dropped `seed` counts → added field (re-approve: created 0 / skipped 8).
- `GET /api/memory` 500 (SQLAlchemy `metadata` collision) → `serialization_alias` fix.
- Kotlin incremental-cache corruption on this PC → `kotlin.incremental=false`.
- Restored two accidental line deletions immediately (models `__tablename__`, `analyzeIncident`).

## 2. Database part
- **Project:** new dev project `qxhwsuzzdwjmpfdqwwri` (ap-south-1), Supabase MCP connected + OAuth.
- **Migrations applied (CREATE IF NOT EXISTS only, nothing dropped):**
  `backend/db/schema.sql` (10 tables) → `001_factory_profile.sql` → `002_app_users.sql` → `003_notifications.sql` → `004_work_plans.sql`.
- **16 tables live:** employees, machines, orders, tasks, production_runs, machine_telemetry, maintenance, incidents, factory_memory, ai_recommendations, factory_profile, app_users, notifications, work_plans, plan_assignments, fcm_tokens.
- **Connection fix:** `.env` repointed from dead host to Session pooler URI (password percent-encoded `%40…%23`); direct `db.*` host is IPv6-only/unresolvable here. Backend binds `0.0.0.0:8000` for phone access. RLS intentionally OFF (backend uses postgres role; revisit for prod).
- **Verified live:** onboarding idempotency, import counts + bad-row reporting, 1 linked HIGH incident on abnormal ingest, 503 AI degradation, decision→memory→maintenance→409 chain, dispatch matching + idempotency, all TEST residue cleaned (8 canonical machines intact).

## 3. Still pending (needs human)
- Supabase Auth user (Authentication → Add user → auto-confirm ON) — unblocks all click-through proof.
- `LLM_API_KEY` in `.env` — unblocks real AI answers (OpenAI or compatible via `LLM_BASE_URL`).
- Firebase project (`google-services.json` + backend env) — unblocks real push (bell fallback works now).

## 4. Future buildable items
1. **Policy-based auto-approval** (bounded autonomy: pre-authorized MONITOR-class actions, full audit).
2. **Closed-loop optimization** (auto re-plan on breakdown, undo support).
3. **Voice-recognition AI assistant** — hands-free control for the shop floor and the boss:
   - Voice input on web (Web Speech API) and Flutter app (speech-to-text package) feeding the existing `POST /ai/chat` endpoint — no new AI plumbing, just a new input modality.
   - Spoken replies via text-to-speech for machine status, at-risk orders, and incident summaries ("Machine 3 is overheating, order 12 is late").
   - Noise-robust design for factory floors (push-to-talk button, confirmation repeat-back before any Apply action; voice NEVER bypasses the approval gate).
   - Multilingual roadmap: English first, Kannada/regional languages next for workers.
4. **Cost/money view** (order margins, downtime cost) on boss dashboard.
5. **Email/SMS alerts** alongside the bell.
6. **iOS build** of the worker app; kiosk/operator tablet view.
7. **Multi-factory support** (factory_id scoping) + RLS policies for prod.
8. **Alembic migrations** to replace hand-run SQL; seed scripts; automated tests; Docker.
9. **Smart Split** (auto order→task splitting) wiring; spare-parts inventory.
