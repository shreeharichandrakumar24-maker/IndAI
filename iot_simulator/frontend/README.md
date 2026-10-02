# IndAI IoT Simulator

> **Superseded for daily use (Phase 4).** The main app now has a built-in,
> manager-gated **Simulator** page with the same seed + transmit + abnormal
> pinning. This standalone app (port 5174) is kept for reference only.

React + Vite web app that simulates a factory floor and sends machine
telemetry to the IndAI FastAPI backend.

## What it does

- Displays a factory-floor schematic with multiple machines.
- Click a machine to select it and view/controll its sensors.
- Manually change telemetry values (temperature, vibration, current,
  RPM, status) to simulate normal or abnormal conditions.
- Transmits telemetry for all machines every 10 seconds via
  `POST /api/telemetry`.
- Loads machines via `GET /api/machines` (seeds the 8-machine demo
  fleet for missing M-001…M-008 codes only — restarts never duplicate).
  Retries automatically if the backend was offline at startup.
- Shows backend connected/offline status, last transmission results,
  and a countdown to the next transmission.

The simulator communicates **only** with FastAPI over HTTP REST.
It **never** connects directly to PostgreSQL.

## Install

```bash
npm install
```

## Run

```bash
npm run dev
```

Expected port: **5174** (see `vite.config.js`).

## Configuration

Backend URL is configured with:

```
VITE_API_BASE_URL=http://localhost:8000
```

(see `.env`). The API base defaults to `http://localhost:8000` if unset.

## Telemetry

One payload per machine every 10 seconds:

- `machine_id`
- `temperature`
- `vibration`
- `current`
- `rpm`
- `machine_status`
- `timestamp`

Backend failures are shown in the transmission log without crashing;
the next cycle retries automatically.
