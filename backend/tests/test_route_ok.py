"""Roadmap step 1: "It's OK – I know" on route alerts + "Pause route alerts" – nothing safety-critical is paused,
every pause ends by itself, and "regular route" is learned at once."""
import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import ai, notify
from app.db import SessionLocal
from app.main import app
from app.models import AiAlert, Device, Location, RouteModel

A = {"X-Admin-Key": "test-admin"}
HOME, FAR = (12.9500, 77.6400), (12.9900, 77.7000)        # FAR is ~7 km from the usual corridor


def _user(c, email):
    return {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": email, "name": email.split("@")[0],
                                                                           "password": "secret123"}).json()["access_token"]}


def _report(db, dev, pos, ts):
    """One location report through the route check (same as the telemetry path)."""
    db.add(Location(device_pk=dev.id, ts=ts, lat=pos[0], lon=pos[1], speed=5))
    dev.last_lat, dev.last_lon, dev.last_seen = pos[0], pos[1], ts
    ai.check(db, dev, ai.device_users(db, dev) if hasattr(ai, "device_users") else [m.user for m in dev.members],
             pos[0], pos[1], 5, ts, "guardian")
    db.commit()


def _route_alerts(db, dev):
    return db.query(AiAlert).filter(AiAlert.device_pk == dev.id, AiAlert.kind.in_(sorted(ai.ROUTE_KINDS))).count()


def _reset_cooldown(db, dev):
    dev.ai_alert_at, dev.ai_offroute = None, 0
    db.commit()


def test_its_ok_pause_and_learn(monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "push", lambda users, title, body, data, **k:
                        sent.extend((u.email, title, data.get("type")) for u in users))
    with TestClient(app) as c:
        mom, dad = _user(c, "rok-mom@x.com"), _user(c, "rok-dad@x.com")
        prov = c.post("/api/admin/devices", json={"device_id": "SX-ROK"}, headers=A).json()
        c.post("/api/devices/claim", headers=mom, json={"device_id": "SX-ROK", "claim_code": prov["claim_code"], "name": "Babai"})
        c.post("/api/devices/SX-ROK/share", headers=mom, json={"email": "rok-dad@x.com"})
        c.post("/api/devices/SX-ROK/geofences", headers=mom, json={"name": "Home", "lat": HOME[0], "lon": HOME[1], "radius_m": 150})
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            dev = db.query(Device).filter_by(device_id="SX-ROK").one()
            ci, cj = ai.cell(*HOME)
            usual = [ai._key((ci + a, cj + b)) for a in range(-2, 3) for b in range(-2, 3)]
            db.add(RouteModel(device_pk=dev.id, cells=json.dumps(usual), places="[]", trips="{}", days=10, updated_at=now))
            db.commit()

            # 1) normal: off the usual corridor twice -> one unusual-route alert
            _report(db, dev, FAR, now - timedelta(minutes=4))
            _report(db, dev, FAR, now - timedelta(minutes=3))
            assert _route_alerts(db, dev) == 1
            _reset_cooldown(db, dev)

        # 2) mom taps "It's OK" (this trip) -> dad is told, no more route alerts on this trip
        sent.clear()
        r = c.post("/api/devices/SX-ROK/route-ok", headers=mom, json={}).json()
        assert r["trip"] is True and r["until"]
        assert ("rok-dad@x.com", "✅ Babai's trip marked OK", "route_ok") in sent
        assert not any(e == "rok-mom@x.com" for e, _, _ in sent)                    # not told about her own tap
        assert c.get("/api/devices/SX-ROK/now", headers=dad).json()["route_paused_trip"] is True
        with SessionLocal() as db:
            dev = db.query(Device).filter_by(device_id="SX-ROK").one()
            _report(db, dev, FAR, now - timedelta(minutes=2))
            _report(db, dev, FAR, now - timedelta(minutes=1))
            assert _route_alerts(db, dev) == 1                                       # still only the first one
            # safety-critical alerts are never paused
            ai._alert(db, dev, [m.user for m in dev.members], "battery", bat=40, empty_at="18:00")
            db.commit()
            assert db.query(AiAlert).filter_by(device_pk=dev.id, kind="battery").count() == 1

            # 3) the trip ends at a known place -> pause cleared -> a new unusual trip alerts again
            _report(db, dev, HOME, now)
            db.refresh(dev)
            assert dev.route_ok_until is None
            _reset_cooldown(db, dev)
            _report(db, dev, FAR, now + timedelta(minutes=1))
            _report(db, dev, FAR, now + timedelta(minutes=2))
            assert _route_alerts(db, dev) == 2

        # 4) timed pause from the map (max 8 h) is NOT ended by arriving home; Resume ends it
        r = c.post("/api/devices/SX-ROK/route-ok", headers=mom, json={"hours": 100}).json()
        assert r["trip"] is False
        with SessionLocal() as db:
            dev = db.query(Device).filter_by(device_id="SX-ROK").one()
            left = (ai.as_utc(dev.route_ok_until) - datetime.now(timezone.utc)).total_seconds() / 3600
            assert 7.9 < left <= 8.0
            _report(db, dev, HOME, now + timedelta(minutes=3))
            db.refresh(dev)
            assert ai.route_paused(dev)
        assert c.delete("/api/devices/SX-ROK/route-ok", headers=mom).json()["ok"]
        # any duration in minutes (15 min – 8 h), clamped
        c.post("/api/devices/SX-ROK/route-ok", headers=mom, json={"minutes": 5})
        with SessionLocal() as db:
            dev = db.query(Device).filter_by(device_id="SX-ROK").one()
            left = (ai.as_utc(dev.route_ok_until) - datetime.now(timezone.utc)).total_seconds() / 60
            assert 14 < left <= 15 and dev.route_ok_trip is False
        c.post("/api/devices/SX-ROK/route-ok", headers=mom, json={"minutes": 150})
        with SessionLocal() as db:
            dev = db.query(Device).filter_by(device_id="SX-ROK").one()
            assert 149 < (ai.as_utc(dev.route_ok_until) - datetime.now(timezone.utc)).total_seconds() / 60 <= 150
        c.delete("/api/devices/SX-ROK/route-ok", headers=mom)
        assert c.get("/api/devices/SX-ROK/now", headers=mom).json()["route_paused_until"] is None

        # 5) "This is a regular route": the cells of the last 3 h count as usual at once and survive relearning
        r = c.post("/api/devices/SX-ROK/route-ok", headers=mom, json={"learn": True}).json()
        assert r["learned_points"] >= 2
        with SessionLocal() as db:
            dev = db.query(Device).filter_by(device_id="SX-ROK").one()
            model = db.query(RouteModel).filter_by(device_pk=dev.id).one()
            assert ai._key(ai.cell(*FAR)) in ai.extra_cells(model)
            ai.learn(db, dev)
            db.commit()
            db.refresh(model)
            assert ai._key(ai.cell(*FAR)) in ai.extra_cells(model)                   # kept on relearn
            dev.route_ok_until = None
            model.days, model.updated_at = 10, datetime.now(timezone.utc)
            db.commit()
            _reset_cooldown(db, dev)
            before = _route_alerts(db, dev)
            _report(db, dev, FAR, now + timedelta(minutes=5))
            _report(db, dev, FAR, now + timedelta(minutes=6))
            assert _route_alerts(db, dev) == before                                  # learned -> no alert
            # the alert list shows who silenced what
            kinds = [a.kind for a in db.query(AiAlert).filter_by(device_pk=dev.id)]
            assert "route_ok" in kinds and "route_pause" in kinds


def test_route_ok_needs_access():
    with TestClient(app) as c:
        stranger = _user(c, "rok-stranger@x.com")
        assert c.post("/api/devices/SX-ROK/route-ok", headers=stranger, json={}).status_code in (403, 404)
