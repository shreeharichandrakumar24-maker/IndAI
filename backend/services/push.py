"""Push delivery for dispatch (Phase 7).

Tries FCM HTTP v1 via firebase-admin ONLY when fully configured
(FIREBASE_CREDENTIALS_JSON + FIREBASE_PROJECT_ID). Otherwise returns
"skipped" and the caller falls back to the in-app bell — never an error,
never a fake "sent".
"""
from typing import Dict, List


def push_configured() -> bool:
    import os
    return bool(os.environ.get("FIREBASE_CREDENTIALS_JSON") and os.environ.get("FIREBASE_PROJECT_ID"))


def send_push(tokens: List[str], title: str, body: str, data: Dict[str, str] | None = None) -> Dict:
    """Returns {sent: int, skipped: int, mode: 'fcm'|'fallback'}."""
    if not tokens:
        return {"sent": 0, "skipped": 0, "mode": "fallback"}
    if not push_configured():
        return {"sent": 0, "skipped": len(tokens), "mode": "fallback"}
    try:
        import json
        import firebase_admin
        from firebase_admin import credentials, messaging
        if not firebase_admin._apps:
            import os
            cred = credentials.Certificate(json.loads(os.environ["FIREBASE_CREDENTIALS_JSON"]))
            firebase_admin.initialize_app(cred, {"projectId": os.environ["FIREBASE_PROJECT_ID"]})
        sent = 0
        for tok in tokens:
            try:
                messaging.send(messaging.Message(
                    notification=messaging.Notification(title=title, body=body),
                    data={k: str(v) for k, v in (data or {}).items()},
                    token=tok,
                ))
                sent += 1
            except Exception:
                continue
        return {"sent": sent, "skipped": len(tokens) - sent, "mode": "fcm"}
    except Exception:
        return {"sent": 0, "skipped": len(tokens), "mode": "fallback"}
