# IndAI worker app (Flutter, Android-first)

Worker companion to the IndAI web console: sign in → **My jobs** (plan
dispatches matched to you) → Accept → Start → Done. New assignments arrive
via **FCM push**, with the in-app bell as fallback; the list is cached for
shop-floor offline use.

The backend (FastAPI) owns all logic: matching, notify, push fan-out.
This app is a thin client over `GET /api/assignments/mine`,
`PATCH /api/assignments/{id}`, `POST /api/push-tokens`.

## Prereqs

- Flutter 3.x stable (checked with 3.47)
- Backend running and reachable from the device
- Firebase project (only for push; the app works bell-only without it)

## Configure

| Value | How |
|---|---|
| Backend URL | `--dart-define=API_BASE_URL=http://<host>:8000` (emulator default `http://10.0.2.2:8000`; physical device needs the machine's LAN IP) |
| Supabase URL/key | `--dart-define=SUPABASE_URL=… --dart-define=SUPABASE_ANON_KEY=…` (anon key is publishable by design) |
| Push (FCM) | Firebase console → Android app (`applicationId`, see below) → download `google-services.json` into `android/app/`; backend needs `FIREBASE_CREDENTIALS_JSON` + `FIREBASE_PROJECT_ID` env. Without these, dispatch still notifies via bell and the app shows "push: off". |

## Run

```sh
cd mobile_app
flutter pub get
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000 \
  --dart-define=SUPABASE_URL=https://qxhwsuzzdwjmpfdqwwri.supabase.co \
  --dart-define=SUPABASE_ANON_KEY=<anon-key>
```

`flutter analyze` for lint. The `android/` shell (Gradle, manifest,
`applicationId com.indai.worker`) is created on first `flutter create` /
build in this folder — commit it once generated, plus `google-services.json`
is git-ignored by default template (keep it out of git).

## Manager → worker loop (end to end)

1. Manager creates plan (`POST /api/plans`), approves (creates tasks).
2. Manager dispatches: engine matches skill + availability + machine,
   writes assignments, bells the worker, pushes via FCM where tokens exist.
   Re-dispatch sends nothing new (idempotent).
3. Worker phone buzzes → opens job → Accept → Start → Done.
4. Manager sees task DONE on the web dashboard.
