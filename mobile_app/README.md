# IndAI worker app (Flutter, Android-first)

Worker companion to the IndAI web console: **sign in** (prototype
username + password) → **My Tasks** (your tasks from the backend) → Start →
progress → Complete / Log output / Report a problem → **Me** (profile +
availability switch).

Architecture: Flutter -> FastAPI -> Supabase. This app never contains
Supabase URLs/keys/credentials and never calls Supabase directly; every
screen uses the REST API below. Prototype sign-in - real authentication is
future work.

## Run from "D:\IET project\IndAI"

```powershell
cd mobile_app
flutter pub get
```

Emulator:

```powershell
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

Real phone (same Wi-Fi as the laptop, backend on 0.0.0.0:8000):

```powershell
flutter run --dart-define=API_BASE_URL=http://<laptop-LAN-IP>:8000
```

USB debugging (no Wi-Fi needed):

```powershell
adb reverse tcp:8000 tcp:8000
flutter run --dart-define=API_BASE_URL=http://127.0.0.1:8000
```

Install a debug APK: `flutter build apk --debug --dart-define=API_BASE_URL=...`
then `flutter install`. `flutter analyze` for lint.

## Windows firewall note (real phone over Wi-Fi)

If the app cannot reach the laptop, allow inbound TCP 8000 in an
**admin** PowerShell (one time):

```powershell
netsh advfirewall firewall add rule name="IndAI 8000" dir=in action=allow protocol=TCP localport=8000
```

## Dev-only cleartext HTTP

`android/.../network_security_config.xml` permits cleartext HTTP because the
dev backend serves plain HTTP. Production must use HTTPS and set
`cleartextTrafficPermitted="false"`. If the app is also run as Flutter web,
add the web origin to the backend CORS list first (development only).

## Demo login

Backend script `python -m backend.scripts.seed_employees` creates 15 demo
workers; usernames/passwords live ONLY in the gitignored
`docs/demo_worker_credentials.txt`. Sign in on the phone with one of those
pairs, e.g. username `arun.prakash`.

## Screens and endpoints used (prototype worker-token auth)

- Login: `POST /api/worker-auth/login` (`identifier` = email, employee code
  or username; generic 401, 429 after abuse) → Bearer token in secure
  storage, sent as `Authorization: Bearer <token>`; 401 anywhere signs out.
- Change password: `POST /api/worker-auth/change-password`
  (`current_password`, `new_password` min 8 chars; forced when the login
  response has `must_change_password: true`).
- Home: `GET /api/worker/me` (profile + task stats).
- My Tasks: `GET /api/worker/tasks` (caller's tasks only, newest first;
  pull-to-refresh, ~15 s poll, new-task indicator).
- Task detail: `GET /api/worker/tasks/{id}` (includes `latest_telemetry`),
  `PUT /api/worker/tasks/{id}/status` (PENDING → IN_PROGRESS → COMPLETED),
  `PUT /api/worker/tasks/{id}/progress` (0..1),
  `POST /api/worker/tasks/{id}/output` (`quantity`, `confirm` over target;
  reads runs via `GET /api/production?order_id=` + `PUT /api/production/{id}`),
  telemetry via `GET /api/telemetry/{machine}?limit=1` (stale-marked).
- Report a problem: `POST /api/worker/incidents` (`LOW/MEDIUM/HIGH/CRITICAL`,
  `[Worker report]` prefix + worker name, machine/task/order links).
- Alerts: `GET /api/worker/alerts` (OPEN incidents touching caller's work).
- Profile: `PUT /api/worker/availability` (`AVAILABLE/BUSY/UNAVAILABLE`);
  sign-out is local-only (token deleted from secure storage).
- Push (unwired): `POST /api/push-tokens` registered by `registerPushToken`;
  `lib/services/push.dart` is currently not called from `main.dart`.
