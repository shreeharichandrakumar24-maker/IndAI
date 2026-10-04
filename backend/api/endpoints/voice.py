"""Voice token minting (Part C). Prefix /voice. No auth.

POST /token -> {url, token, room, identity}: fresh room "indai-<random>",
identity "admin-<random>", ~10 min TTL, join+publish+subscribe+data grants,
and EXPLICIT dispatch of the agent by VOICE_AGENT_NAME. Missing LIVEKIT_* ->
503. The secret is never returned or logged.
"""
import secrets
from datetime import timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.config import settings

router = APIRouter()


class VoiceToken(BaseModel):
    url: str
    token: str
    room: str
    identity: str


class VoiceStatus(BaseModel):
    configured: bool
    agent_name: str
    missing: list[str] = []


@router.post("/token", response_model=VoiceToken)
def mint_voice_token():
    if not (settings.LIVEKIT_URL and settings.LIVEKIT_API_KEY and settings.LIVEKIT_API_SECRET):
        raise HTTPException(status_code=503, detail="Voice not configured")
    try:
        from livekit.api import AccessToken, RoomAgentDispatch, RoomConfiguration, VideoGrants
    except ImportError:
        raise HTTPException(status_code=503, detail="Voice not configured")
    room = f"indai-{secrets.token_hex(4)}"
    identity = f"admin-{secrets.token_hex(4)}"
    token = (
        AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_grants(VideoGrants(room_join=True, room=room,
                                can_publish=True, can_subscribe=True, can_publish_data=True))
        .with_room_config(RoomConfiguration(
            agents=[RoomAgentDispatch(agent_name=settings.VOICE_AGENT_NAME)]))
        .with_ttl(timedelta(seconds=600))
        .to_jwt()
    )
    return VoiceToken(url=settings.LIVEKIT_URL, token=token, room=room, identity=identity)


@router.get("/status", response_model=VoiceStatus)
def voice_status():
    """Voice readiness without secrets: which variable NAMES are missing."""
    missing = [v for v in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
               if not (getattr(settings, v, "") or "").strip()]
    return VoiceStatus(configured=not missing,
                       agent_name=settings.VOICE_AGENT_NAME, missing=missing)
