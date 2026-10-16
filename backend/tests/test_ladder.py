"""Child SOS ladder: parents now -> other family after 2 min -> school after 5 min."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import notify
from app.db import SessionLocal
from app.main import app
from app.models import SosEvent
from app.services_help import check_escalations


def test_sos_ladder(monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "push", lambda users, title, body, data, **k: sent.append(({u.email for u in users}, title)))
    with TestClient(app) as c:
        A = {"X-Admin-Key": "test-admin"}
        prov = c.post("/api/admin/devices", json={"device_id": "SX-L1"}, headers=A).json()
        reg = lambda e: {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": e, "name": e[:3],
                                                                                         "password": "secret123"}).json()["access_token"]}
        dad, gm = reg("dad@l.com"), reg("gma@l.com")
        c.post("/api/devices/claim", headers=dad, json={"device_id": "SX-L1", "claim_code": prov["claim_code"], "name": "Kid"})
        c.post("/api/devices/SX-L1/share", headers=dad, json={"email": "gma@l.com"})
        dh = {"X-Device-Id": "SX-L1", "X-Device-Secret": prov["device_secret"]}
        sent.clear()
        c.post("/api/device/telemetry", headers=dh, json={"lat": 12.97, "lon": 77.59, "sos": 1})
        assert [s for s in sent if "SOS" in s[1]] == [({"dad@l.com"}, "🚨 SOS ALERT")]          # parents first
        with SessionLocal() as db:
            ev = db.query(SosEvent).order_by(SosEvent.id.desc()).first()
            ev.started_at = datetime.now(timezone.utc) - timedelta(minutes=3)
            db.commit()
            sent.clear()
            check_escalations(db)
        assert ({"gma@l.com"}, "🚨 SOS ALERT") in sent                                           # then family
        with SessionLocal() as db:
            ev = db.query(SosEvent).order_by(SosEvent.id.desc()).first()
            assert ev.family_notified_at is not None and ev.school_notified_at is None          # school not yet
            ev.started_at = datetime.now(timezone.utc) - timedelta(minutes=6)
            db.commit()
            check_escalations(db)
            ev = db.query(SosEvent).order_by(SosEvent.id.desc()).first()
            assert ev.school_notified_at is not None                                            # then school
