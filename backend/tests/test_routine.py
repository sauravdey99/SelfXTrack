"""Learned trip times, ETA, late arrival, did-not-leave and missed-place alerts."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import ai
from app.db import SessionLocal
from app.main import app
from app.models import AiAlert, Device, Location

SCHOOL, HOME = (12.9300, 77.6200), (12.9500, 77.6400)          # ~3 km apart


def walk(db, dev, t0, a, b, minutes, step=5):
    n = minutes // step
    for i in range(1, n):
        f = i / n
        db.add(Location(device_pk=dev.id, ts=t0 + timedelta(minutes=step * i), lat=a[0] + (b[0] - a[0]) * f,
                        lon=a[1] + (b[1] - a[1]) * f, speed=8))


def stay(db, dev, t0, p, minutes, step=10):
    for i in range(0, minutes + 1, step):
        db.add(Location(device_pk=dev.id, ts=t0 + timedelta(minutes=i), lat=p[0], lon=p[1], speed=0))


def test_routine_alerts():
    with TestClient(app) as c:
        prov = c.post("/api/admin/devices", json={"device_id": "SX-R1"}, headers={"X-Admin-Key": "test-admin"}).json()
        h = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": "r1@example.com", "name": "R",
                                                                            "password": "secret123"}).json()["access_token"]}
        c.post("/api/devices/claim", headers=h, json={"device_id": "SX-R1", "claim_code": prov["claim_code"], "name": "Babai"})
        c.post("/api/admin/users/plan", headers={"X-Admin-Key": "test-admin"}, json={"email": "r1@example.com", "plan": "smart"})
        c.post("/api/devices/SX-R1/geofences", headers=h, json={"name": "School", "lat": SCHOOL[0], "lon": SCHOOL[1], "radius_m": 100})
        c.post("/api/devices/SX-R1/geofences", headers=h, json={"name": "Home", "lat": HOME[0], "lon": HOME[1], "radius_m": 100})
        hol = c.post("/api/devices/SX-R1/holidays", headers=h, json={"start": "2099-05-01", "end": "2099-05-03"}).json()
        assert [x["day"] for x in hol if not x["public"]] == ["2099-05-01", "2099-05-02", "2099-05-03"]
        assert len([x for x in c.delete("/api/devices/SX-R1/holidays/2099-05-02", headers=h).json() if not x["public"]]) == 2
        c.put("/api/devices/SX-R1/setup", headers=h, json={"public_holidays": False})   # synthetic data on real dates

        # "now" = 11:00 IST today; routine every past day: School until 10:00, 25-min trip, Home from 10:25
        ist = ai.tz()
        today = datetime.now(ist).date()
        T = lambda d, hh, mm: datetime(d.year, d.month, d.day, hh, mm, tzinfo=ist).astimezone(timezone.utc)
        with SessionLocal() as db:
            dev = db.query(Device).filter_by(device_id="SX-R1").one()
            for k in range(1, 8):
                d = today - timedelta(days=k)
                stay(db, dev, T(d, 8, 0), SCHOOL, 120)                  # 08:00-10:00 school
                walk(db, dev, T(d, 10, 0), SCHOOL, HOME, 25)            # 25 min
                stay(db, dev, T(d, 10, 25), HOME, 90)                   # home
            db.commit()
            m = ai.learn(db, dev)
            db.commit()
            trips = __import__("json").loads(m.trips)["trips"]
            t = next(x for x in trips if x["from"] == "School" and x["to"] == "Home")
            assert t["count"] == 7 and 20 <= t["median_min"] <= 30 and t["usual_depart"] == "10:00"

            # TODAY A: at school, 10:50 -> "hasn't left School"
            stay(db, dev, T(today, 8, 0), SCHOOL, 170)
            dev.last_lat, dev.last_lon, dev.last_seen = SCHOOL[0], SCHOOL[1], T(today, 10, 50)
            db.commit()
            # first: gentle "holiday today?" question instead of alarms
            assert ai.check_routine(db, dev, [], T(today, 10, 50)) == ["holiday_q"]
            assert ai.check_routine(db, dev, [], T(today, 10, 52)) == []          # waiting for answer
            # parent says "not a holiday" -> normal alert
            from app.models import User as U
            parent = db.query(U).filter_by(email="r1@example.com").one()
            ai.answer_holiday(db, dev, parent, False)
            db.commit()
            assert ai.check_routine(db, dev, [], T(today, 10, 53)) == ["noleave"]
            assert ai.check_routine(db, dev, [], T(today, 10, 55)) == []          # once per day
            # holiday set for today -> routine alerts pause; holiday days are not learned
            ai.set_holidays(db, dev, parent, [today])
            db.commit()
            db.query(AiAlert).delete()
            db.commit()
            assert ai.check_routine(db, dev, [], T(today, 10, 56)) == []
            db.query(__import__("app.models", fromlist=["Holiday"]).Holiday).delete()
            db.commit()
            ai.answer_holiday(db, dev, parent, False)
            db.commit()

            # TODAY B: left school 10:52, 11:35 still 1 km away -> late; ETA uses learned 25 min
            walk(db, dev, T(today, 10, 52), SCHOOL, (12.9430, 77.6330), 40)
            dev.last_lat, dev.last_lon = 12.9430, 77.6330
            dev.last_seen = T(today, 11, 32)
            db.commit()
            st = ai.trip_state(db, dev, T(today, 11, 35))
            assert st["state"] == "moving" and st["from"] == "School" and st["trip"]["to"] == "Home"
            fired = ai.check_routine(db, dev, [], T(today, 11, 35))
            assert "late" in fired

            # detour + vehicle speed + lingering on a NEW trip today (fresh dedupe keys)
            db.query(AiAlert).delete()
            dev.last_speed = 40                               # usually walks ~8 km/h
            dev.last_lat, dev.last_lon = 12.9300, 77.6500     # ~2.7 km east of the School->Home line
            dev.stop_lat, dev.stop_lon, dev.stop_since = 12.9300, 77.6500, T(today, 11, 20)
            db.add(Location(device_pk=dev.id, ts=T(today, 11, 33), lat=12.9300, lon=77.6500, speed=40))
            db.commit()
            st = ai.trip_state(db, dev, T(today, 11, 36))
            assert st["state"] == "moving" and st["trip"]["to"] == "Home"
            f1 = ai.check_routine(db, dev, [], T(today, 11, 36))
            f2 = ai.check_routine(db, dev, [], T(today, 11, 37))
            assert "speed" in f1 and "linger" in f1 and "detour" in (f1 + f2)
            assert any(a.kind == "late" and "still" in a.text for a in db.query(AiAlert).all())
            dev.last_seen = datetime.now(timezone.utc)
            db.commit()

        ask = lambda q: c.post("/api/devices/SX-R1/ask", headers=h, json={"question": q}).json()["answer"]
        assert "Babai has not been at Home" in ask("did he reached home ?")
        assert "Babai reached School" in ask("did he reach the school today?") or "Babai has been at School" in ask("did he reach the school today?")
        assert "No SOS" in ask("is he safe now ?")
        assert "Home" in ask("when babai will come home ?")
        with SessionLocal() as db:
            dev = db.query(Device).filter_by(device_id="SX-R1").one()
            e = ai.expected_place(db, dev, T(today, 12, 0))
            assert e["place"] == "Home" and e["since"] == "10:25"
            e = ai.expected_place(db, dev, T(today, 9, 0))
            assert e["place"] == "School" and e["next"]["to"] == "Home"
            dev.last_seen = datetime.now(timezone.utc) - timedelta(hours=12)
            db.commit()
        off = ask("where is he now?")
        assert "OFFLINE" in off and "By routine" in off
        assert "Battery" in ask("battery?")
        rows = c.get("/api/devices/SX-R1/days", headers=h).json()
        assert [r["label"] for r in rows] == ["Today", "Yesterday"] and rows[1]["status"] == "normal"
        wk = (today - timedelta(days=6)).isoformat()
        assert len(c.get(f"/api/devices/SX-R1/days?start={wk}&end={today.isoformat()}", headers=h).json()) == 7
        # Basic: today/yesterday OK, custom dates locked
        c.post("/api/admin/users/plan", headers={"X-Admin-Key": "test-admin"}, json={"email": "r1@example.com", "plan": "basic"})
        assert c.get("/api/devices/SX-R1/days", headers=h).status_code == 200
        assert c.get(f"/api/devices/SX-R1/days?start={wk}&end={today.isoformat()}", headers=h).status_code == 402
        assert c.get(f"/api/devices/SX-R1/day?day={rows[1]['date']}", headers=h).status_code == 200
        d = c.get(f"/api/devices/SX-R1/day?day={rows[1]['date']}", headers=h).json()
        kinds = [x["kind"] for x in d["timeline"]]
        assert kinds[:3] == ["stay", "travel", "stay"] and d["timeline"][1]["title"] == "School → Home" and d["path"]
