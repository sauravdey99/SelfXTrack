"""Push notifications (Firebase Cloud Messaging) + logging.

Enable FCM:
  1. Firebase console -> Project settings -> Service accounts -> Generate new private key (JSON)
  2. pip install firebase-admin
  3. export SELFX_FCM_CREDENTIALS=/path/to/service-account.json
Without it, notifications are only logged and sent over WebSocket.
"""
import logging

from .config import settings
from .models import User

log = logging.getLogger("selfx.notify")
_fcm_ready: bool | None = None


def _init_fcm() -> bool:
    global _fcm_ready
    if _fcm_ready is not None:
        return _fcm_ready
    _fcm_ready = False
    if not settings.fcm_credentials:
        return False
    try:
        import firebase_admin
        from firebase_admin import credentials
        firebase_admin.initialize_app(credentials.Certificate(settings.fcm_credentials))
        _fcm_ready = True
        log.info("FCM enabled")
    except Exception as e:
        log.warning("FCM not available: %s", e)
    return _fcm_ready


def send_fcm(token: str, title: str, body: str, data: dict, urgent: bool) -> None:
    if not _init_fcm():
        return
    from firebase_admin import messaging
    try:
        # Data-only message so the app always builds the notification itself (full-screen SOS etc.)
        msg = messaging.Message(token=token, data={**data, "title": title, "body": body},
                                android=messaging.AndroidConfig(priority="high", ttl=3600))
        messaging.send(msg)
    except Exception as e:
        log.warning("FCM send failed: %s", e)


def push(users: list[User], title: str, body: str, data: dict | None = None) -> None:
    data = {k: "" if v is None else str(v) for k, v in (data or {}).items()}
    urgent = data.get("type") == "sos"
    seen = set()
    for u in users:
        if u.id in seen:
            continue
        seen.add(u.id)
        log.warning("NOTIFY user=%s | %s | %s", u.email, title, body)
        if u.fcm_token:
            send_fcm(u.fcm_token, title, body, data, urgent)
