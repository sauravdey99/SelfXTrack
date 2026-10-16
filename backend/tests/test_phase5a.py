"""Phase 5 batch A: parent role, public holidays, battery forecast, weekly report."""
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import ai, notify
from app.db import SessionLocal
from app.main import app
from app.models import Device, Location, SosEvent
from app.services_help import check_escalations


def reg(c, e, phone):
    h = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": e, "name": e[:4], "password": "secret123"}).json()["access_token"]}
    code = c.post("/api/auth/otp/request", headers=h, json={"phone": phone}).json()["dev_code"]
    c.post("/api/auth/otp/verify", headers=h, json={"phone": phone, "code": code})
    return h


def test_batch_a(monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "push", lambda users, title, body, data, **k: sent.append(({u.email for u in users}, title)))
    with TestClient(app) as c:
        A = {"X-Admin-Key": "test-admin"}
        prov = c.post("/api/admin/devices", json={"device_id": "SX-5A"}, headers=A).json()
        dad, mom, gpa = reg(c, "dad5@x.com", "9100000001"), reg(c, "mom5@x.com", "9100000002"), reg(c, "gpa5@x.com", "9100000003")
        c.post("/api/devices/claim", headers=dad, json={"device_id": "SX-5A", "claim_code": prov["claim_code"], "name": "Riya"})
        c.post("/api/devices/SX-5A/family-invites", headers=dad, json={"name": "Mom", "phone": "9100000002", "relation": "parent"})
        c.post("/api/devices/SX-5A/family-invites", headers=dad, json={"name": "Grandpa", "phone": "9100000003"})
        st = c.get("/api/devices/SX-5A/setup", headers=dad).json()
        assert {i["name"]: i["relation"] for i in st["invites"]} == {"Mom": "parent", "Grandpa": "family"}
        for i in st["invites"]:
            st = c.post(f"/api/devices/SX-5A/family-invites/{i['id']}/accept", headers=dad).json()
        assert {f["role"] for f in st["family"]} == {"owner", "parent", "family"}

        # SOS: dad + mom ring at once, grandpa after 2 min
        dh = {"X-Device-Id": "SX-5A", "X-Device-Secret": prov["device_secret"]}
        sent.clear()
        c.post("/api/device/telemetry", headers=dh, json={"lat": 12.97, "lon": 77.59, "sos": 1})
        assert ({"dad5@x.com", "mom5@x.com"}, "🚨 SOS ALERT") in sent
        with SessionLocal() as db:
            ev = db.query(SosEvent).order_by(SosEvent.id.desc()).first()
            ev.started_at = datetime.now(timezone.utc) - timedelta(minutes=3)
            db.commit()
            sent.clear()
            check_escalations(db)
        assert ({"gpa5@x.com"}, "🚨 SOS ALERT") in sent

        # change grandpa to parent
        st = c.put("/api/devices/SX-5A/family/9100000003/role", headers=dad, json={"relation": "parent"}).json()
        assert all(f["role"] in ("owner", "parent") for f in st["family"])

        # public holiday calendar
        with SessionLocal() as db:
            dev = db.query(Device).filter_by(device_id="SX-5A").one()
            assert ai.is_holiday(db, dev, date(2026, 8, 15)) and not ai.is_holiday(db, dev, date(2026, 8, 14))
            dev.public_holidays = False
            db.commit()
            assert not ai.is_holiday(db, dev, date(2026, 8, 15))

            # battery forecast: 80% -> 50% over 3 h = 10 %/h -> ~5 h left
            now = datetime.now(timezone.utc)
            for k, b in enumerate([80, 70, 60, 50]):
                db.add(Location(device_pk=dev.id, ts=now - timedelta(hours=3 - k), lat=12.97, lon=77.59, battery=b))
            dev.battery, dev.charging = 50, False
            db.commit()
            f = ai.battery_forecast(db, dev, now)
            assert 4 <= f["hours_left"] <= 6 and "run out" in f["text"]
            assert ai.check_battery(db, dev, [], now) is False            # > 3 h left: no warning
            dev.battery = 25
            db.commit()
            assert ai.check_battery(db, dev, [], now) is True and ai.check_battery(db, dev, [], now) is False

        c.post("/api/admin/users/plan", headers=A, json={"email": "dad5@x.com", "plan": "smart"})
        w = c.get("/api/devices/SX-5A/weekly", headers=dad).json()
        assert "Week of" in w["text"] and w["sos"] >= 1
