"""Family screen at-a-glance: at School since 08:04 (on time), until 16:00, next Home; moving: trip + mode; alerts."""
import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import ai
from app.db import SessionLocal
from app.main import app
from app.models import AiAlert, Device, Geofence, Location

A = {"X-Admin-Key": "test-admin"}
SCHOOL, HOME = (12.9300, 77.6200), (12.9500, 77.6400)


def test_family_brief():
    ist = ai.tz()
    now = datetime.now(timezone.utc)
    with TestClient(app) as c:
        h = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": "br@x.com", "name": "P",
                                                                            "password": "secret123"}).json()["access_token"]}
        prov = c.post("/api/admin/devices", json={"device_id": "SX-BR"}, headers=A).json()
        c.post("/api/devices/claim", headers=h, json={"device_id": "SX-BR", "claim_code": prov["claim_code"], "name": "Babai"})
        c.post("/api/devices/SX-BR/geofences", headers=h, json={"name": "School", "lat": SCHOOL[0], "lon": SCHOOL[1], "radius_m": 100})
        c.post("/api/devices/SX-BR/geofences", headers=h, json={"name": "Home", "lat": HOME[0], "lon": HOME[1], "radius_m": 100})
        assert c.get("/api/family/brief", headers=h).json()[0]["state"] == "never"

        arrived = now - timedelta(minutes=50)
        a_l = arrived.astimezone(ist)
        start = (a_l - timedelta(minutes=2)).strftime("%H:%M")              # slot started 2 min before arrival
        end = (now.astimezone(ist) + timedelta(minutes=30)).strftime("%H:%M")
        nxt = (now.astimezone(ist) + timedelta(minutes=60)).strftime("%H:%M")
        with SessionLocal() as db:
            dev = db.query(Device).filter_by(device_id="SX-BR").one()
            for g in db.query(Geofence).filter_by(device_pk=dev.id):
                if g.name == "School" and start < end:
                    g.schedule = json.dumps([{"days": [a_l.weekday()], "start": start, "end": end}])
                if g.name == "Home" and nxt > end:
                    g.schedule = json.dumps([{"days": [a_l.weekday()], "start": nxt, "end": "23:59"}])
            for i in range(0, 51, 10):
                db.add(Location(device_pk=dev.id, ts=arrived + timedelta(minutes=i), lat=SCHOOL[0], lon=SCHOOL[1], speed=0, battery=80))
            dev.last_lat, dev.last_lon, dev.last_seen, dev.battery, dev.last_speed = SCHOOL[0], SCHOOL[1], now, 80, 0
            db.add(AiAlert(device_pk=dev.id, kind="route", text="Babai is on an unusual route"))
            db.commit()
        b = c.get("/api/family/brief", headers=h).json()[0]
        assert b["state"] == "at" and b["place"] == "School" and b["since"] == a_l.strftime("%H:%M")
        same_day = (now.astimezone(ist) + timedelta(minutes=60)).date() == a_l.date()   # test times not across midnight
        if start < end and same_day:
            assert b["arrival"] == "on_time" and b["until"] == end
        if nxt > end and same_day:
            assert b["next"] == {"place": "Home", "at": nxt, "source": "schedule"}
        assert b["alerts_today"] == 1 and b["last_alert"]["kind"] == "route"

        # moving: trip from School, cycling
        with SessionLocal() as db:
            dev = db.query(Device).filter_by(device_id="SX-BR").one()
            for i in range(1, 4):
                f = i / 8
                db.add(Location(device_pk=dev.id, ts=now + timedelta(minutes=i), lat=SCHOOL[0] + (HOME[0] - SCHOOL[0]) * f,
                                lon=SCHOOL[1] + (HOME[1] - SCHOOL[1]) * f, speed=12))
            dev.last_lat, dev.last_lon = SCHOOL[0] + (HOME[0] - SCHOOL[0]) * 3 / 8, SCHOOL[1] + (HOME[1] - SCHOOL[1]) * 3 / 8
            dev.last_seen, dev.last_speed = now + timedelta(minutes=3), 12
            db.commit()
            b = ai.brief(db, dev, now=now + timedelta(minutes=3))
        assert b["state"] == "moving" and b["mode"] == "cycling"
        assert b["trip"]["started_from"] == "School" and b["trip"]["heading_to"] == "Home"
