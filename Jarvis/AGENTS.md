# IndAI voice agent

LiveKit voice agent ("Jarvis") for the IndAI factory admin app.

## Run

```powershell
cd Jarvis
.\venv\Scripts\python.exe src\agent.py dev
# or, with uv installed:  uv run src/agent.py dev
```

Needs `Jarvis/.env.local` (copy from `.env.example`): LiveKit Cloud URL/key/secret
plus `INDAI_API_URL=http://localhost:8000/api`. The agent talks to the
backend REST API only; it has no database credentials.

## Safety

Propose-only: the agent creates PENDING proposals. Nothing is applied until
an admin taps Approve in the web app. There is no approve/execute tool.
