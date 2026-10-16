"""School -> Swimming instead of the usual School -> Home: one alert at most, no "late / didn't reach Home" while he is
safely at Swimming, nothing at all when Swimming is on today's schedule, and "It's OK" also covers late / missed."""
import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import ai
from app.db import SessionLocal
from app.main import app
from app.models import AiAlert, Device, Geofence, Location

A = {"X-Admin-Key": "test-admin"}
SCHOOL, HOME, SWIM = (12.9300, 77.6200), (12.9500, 77.6400), (12.9300, 77.6600)   # Swimming ~4.3 km east of School
ROUTE_LIKE = ("route", "detour", "late", "missed", "time", "linger", "stop", "speed")


def _setup(c, n):
    h = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": f"nd{n}@x.com", "name": "P",
                                                                        "password": "secret123"}).json()["access_token"]}
    prov = c.post("/api/admin/devices", json={"device_id": f"SX-ND{n}"}, headers=A).json()
    c.post("/api/devices/claim", headers=h, json={"device_id": f"SX-ND{n}", "claim_code": prov["claim_code"], "name": "Babai"})
    c.post("/api/admin/users/plan", headers=A, json={"email": f"nd{n}@x.com", "plan": "smart"})
    c.put(f"/api/devices/SX-ND{n}/setup", headers=h, json={"public_holidays": False})
    for name, (la, lo) in (("School", SCHOOL), ("Home", HOME), ("Swimming", SWIM)):
        c.post(f"/api/devices/SX-ND{n}/geofences", headers=h, json={"name": name, "lat": la, "lon": lo, "radius_m": 100})
    return h


def _day(db, dev, T, d, dest):
    """School 08:00-16:00, then a 25-min walk to `dest`, then 90 min there."""
    for i in range(0, 481, 10):
        db.add(Location(device_pk=dev.id, ts=T(d, 8, 0) + timedelta(minutes=i), lat=SCHOOL[0], lon=SCHOOL[1], speed=0))
    for i in range(1, 5):
        f = i / 5
        db.add(Location(device_pk=dev.id, ts=T(d, 16, 0) + timedelta(minutes=5 * i), lat=SCHOOL[0] + (dest[0] - SCHOOL[0]) * f,
                        lon=SCHOOL[1] + (dest[1] - SCHOOL[1]) * f, speed=8))
    for i in range(0, 91, 10):
        db.add(Location(device_pk=dev.id, ts=T(d, 16, 25) + timedelta(minutes=i), lat=dest[0], lon=dest[1], speed=0))


def _report(db, dev, pos, ts, spd=8):
    db.add(Location(device_pk=dev.id, ts=ts, lat=pos[0], lon=pos[1], speed=spd))
    dev.last_lat, dev.last_lon, dev.last_seen, dev.last_speed = pos[0], pos[1], ts, spd
    for g in db.query(Geofence).filter_by(device_pk=dev.id):
        g.inside = ai.distance_m(pos[0], pos[1], g.lat, g.lon) <= g.radius_m
    ai.check(db, dev, [], pos[0], pos[1], spd, ts, "smart")
    db.commit()


def _trip_to_swimming(db, dev, T, today, until_min=60):
    """Today: school until 16:00, then the new road to Swimming (arrive 16:25), stay there."""
    for i in range(0, 481, 10):
        db.add(Location(device_pk=dev.id, ts=T(today, 8, 0) + timedelta(minutes=i), lat=SCHOOL[0], lon=SCHOOL[1], speed=0))
    db.commit()
    for i in range(1, 6):
        f = i / 5
        _report(db, dev, (SCHOOL[0] + (SWIM[0] - SCHOOL[0]) * f, SCHOOL[1] + (SWIM[1] - SCHOOL[1]) * f),
                T(today, 16, 0) + timedelta(minutes=5 * i), spd=8 if i < 5 else 0)
    for m in range(30, until_min + 1, 10):
        _report(db, dev, SWIM, T(today, 16, 0) + timedelta(minutes=m), spd=0)


def _kinds(db, dev):
    return [a.kind for a in db.query(AiAlert).filter(AiAlert.device_pk == dev.id, AiAlert.kind.in_(ROUTE_LIKE))]


def _learned(db, dev, T, today):
    for k in range(1, 8):
        _day(db, dev, T, today - timedelta(days=k), HOME)
    db.commit()
    m = ai.learn(db, dev)
    db.commit()
    assert any(t["from"] == "School" and t["to"] == "Home" for t in json.loads(m.trips)["trips"])


def test_new_destination_scenarios():
    ist = ai.tz()
    today = datetime.now(ist).date()
    T = lambda d, hh, mm: datetime(d.year, d.month, d.day, hh, mm, tzinfo=ist).astimezone(timezone.utc)
    with TestClient(app) as c:
        # A) not on the schedule: one "unusual route" alert, then quiet; no "didn't reach Home" while at Swimming
        _setup(c, 1)
        with SessionLocal() as db:
            dev = db.query(Device).filter_by(device_id="SX-ND1").one()
            _learned(db, dev, T, today)
            _trip_to_swimming(db, dev, T, today)
            st = ai.trip_state(db, dev, T(today, 16, 20))
            assert _kinds(db, dev) == ["route"]                                   # one alert, not two
            # 17:15 – usual Home arrival + 45 min, but he is at Swimming -> no "missed"
            assert "missed" not in ai.check_routine(db, dev, [], T(today, 17, 15))
            assert "missed" not in ai.check_routine(db, dev, [], T(today, 18, 0))

        # B) Swimming is on today's schedule (16:30-17:30): the app expects it -> no route alerts at all
        h = _setup(c, 2)
        with SessionLocal() as db:
            dev = db.query(Device).filter_by(device_id="SX-ND2").one()
            sw = db.query(Geofence).filter_by(device_pk=dev.id, name="Swimming").one()
            sw.schedule = json.dumps([{"days": [today.weekday()], "start": "16:30", "end": "17:30"}])
            _learned(db, dev, T, today)
            for i in range(0, 481, 10):
                db.add(Location(device_pk=dev.id, ts=T(today, 8, 0) + timedelta(minutes=i), lat=SCHOOL[0], lon=SCHOOL[1], speed=0))
            db.commit()
            _report(db, dev, (SCHOOL[0], SCHOOL[1] + 0.008), T(today, 16, 5))
            st = ai.trip_state(db, dev, T(today, 16, 5))
            assert st["trip"]["to"] == "Swimming" and st["trip"]["scheduled"]
            for i in range(2, 6):
                f = i / 5
                _report(db, dev, (SCHOOL[0], SCHOOL[1] + (SWIM[1] - SCHOOL[1]) * f), T(today, 16, 0) + timedelta(minutes=5 * i),
                        spd=8 if i < 5 else 0)
            assert _kinds(db, dev) == []

        # C) "It's OK" on the way to an unsaved place (singing class): no "late" / "didn't reach Home" for that trip
        _setup(c, 3)
        with SessionLocal() as db:
            dev = db.query(Device).filter_by(device_id="SX-ND3").one()
            _learned(db, dev, T, today)
            dev.route_ok_until, dev.route_ok_trip = datetime.now(timezone.utc) + timedelta(hours=3), True
            db.commit()
            SING = (12.9150, 77.6200)                                            # 1.7 km south, not a saved place
            for i in range(0, 481, 10):
                db.add(Location(device_pk=dev.id, ts=T(today, 8, 0) + timedelta(minutes=i), lat=SCHOOL[0], lon=SCHOOL[1], speed=0))
            for i in range(1, 6):
                db.add(Location(device_pk=dev.id, ts=T(today, 16, 0) + timedelta(minutes=4 * i),
                                lat=SCHOOL[0] + (SING[0] - SCHOOL[0]) * i / 5, lon=SING[1], speed=8))
            for m in range(20, 81, 10):
                db.add(Location(device_pk=dev.id, ts=T(today, 16, 0) + timedelta(minutes=m), lat=SING[0], lon=SING[1], speed=0))
            dev.last_lat, dev.last_lon, dev.last_seen = SING[0], SING[1], T(today, 17, 20)
            db.commit()
            ai.check_routine(db, dev, [], T(today, 17, 20))
            db.commit()
            assert _kinds(db, dev) == []
            # without the pause the same situation does alert ("hasn't reached Home" – he is at an unknown place)
            dev.route_ok_until = None
            db.commit()
            assert {"late", "missed"} & set(ai.check_routine(db, dev, [], T(today, 17, 20)))
