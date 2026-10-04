"""Prove the voice loop without a browser: mint a token like the web app,
join as a test participant, wait up to 30 s for the agent, report.

Run from Jarvis/:  venv python src/test_join.py
Needs backend running + Jarvis/.env.local with LIVEKIT_* (else exits 2
with the exact missing piece). Never prints secrets.
"""
import asyncio
import json
import os
import sys
import urllib.request

API = os.environ.get("INDAI_API_URL", "http://127.0.0.1:8000/api").rstrip("/")
WAIT_S = int(os.environ.get("JOIN_WAIT_S", "30"))


def post_token():
    req = urllib.request.Request(API + "/voice/token", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            body = json.load(e)
        except Exception:
            body = e.read().decode()[:200]
        return e.code, body


async def main():
    from livekit import rtc

    status, data = post_token()
    if status != 200:
        print(f"JOIN-FAIL token HTTP {status}: {str(data)[:160]}")
        return 2
    url, token, room_name = data["url"], data["token"], data["room"]
    room = rtc.Room()
    seen = []

    @room.on("participant_connected")
    def _on_join(p):
        seen.append(p.identity)

    try:
        await room.connect(url, token)
    except Exception as e:
        print(f"JOIN-FAIL connect: {str(e)[:200]}")
        return 2
    for _ in range(WAIT_S * 2):
        await asyncio.sleep(0.5)
        parts = [p.identity for p in room.remote_participants.values()]
        if parts:
            print(f"JOIN-PASS agent joined: {parts} (room {room_name})")
            await room.disconnect()
            return 0
    print(f"JOIN-FAIL no agent in {WAIT_S}s. Start it with: cd Jarvis, then uv run src/agent.py dev "
          f"(or the venv python directly). Heard joins during wait: {seen}")
    await room.disconnect()
    return 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
