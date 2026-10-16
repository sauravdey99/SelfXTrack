"""Places (any number, with schedules + people), transport, schedule alerts, per-place emergency + visibility,
and the move of older data."""
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import ai, notify, places
from app.db import SessionLocal
from app.main import app
from app.models import AiAlert, Device, DeviceBus, Geofence, TeacherContact

A = {"X-Admin-Key": "test-admin"}
HOME, SCHOOL, SWIM = (12.9500, 77.6400), (12.9300, 77.6200), (12.9400, 77.6000)


def user(c, email, phone=None):
    h = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": email, "name": email.split("@")[0],
                                                                        "password": "secret123"}).json()["access_token"]}
    if phone:
        code = c.post("/api/auth/otp/request", headers=h, json={"phone": phone}).json()["dev_code"]
        c.post("/api/auth/otp/verify", headers=h, json={"phone": phone, "code": code})
    return h


def tracker(c, h, did, name="Babai"):
    prov = c.post("/api/admin/devices", json={"device_id": did}, headers=A).json()
    c.post("/api/devices/claim", headers=h, json={"device_id": did, "claim_code": prov["claim_code"], "name": name})
    return {"X-Device-Id": did, "X-Device-Secret": prov["device_secret"]}


def place(c, h, did, name, kind, pos, schedule=(), **kw):
    r = c.post(f"/api/devices/{did}/places", headers=h, json={"name": name, "kind": kind, "lat": pos[0], "lon": pos[1],
                                                               "radius_m": 150, "schedule": list(schedule), **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_places_crud_validation_and_people():
    with TestClient(app) as c:
        mom = user(c, "pl-mom@x.com", "9000000101")
        tracker(c, mom, "SX-PL1")
        tracker(c, mom, "SX-PL2", "Puchu")
        home = place(c, mom, "SX-PL1", "Home", "home", HOME)
        school = place(c, mom, "SX-PL1", "DPS", "school", SCHOOL, note="5A",
                       schedule=[{"days": [0, 1, 2, 3, 4], "start": "08:00", "end": "14:30"}])
        swim = place(c, mom, "SX-PL1", "Aqua Swim", "activity", SWIM, schedule=[{"days": [5], "start": "07:00", "end": "08:00"}])
        assert school["schedule"][0]["days"] == [0, 1, 2, 3, 4] and school["note"] == "5A"
        listed = c.get("/api/devices/SX-PL1/places", headers=mom).json()
        assert [p["name"] for p in listed] == ["Home", "DPS", "Aqua Swim"]          # home, school, … order
        assert c.get("/api/devices/SX-PL1/setup", headers=mom).json()["manual_school"] == "DPS"

        bad = lambda **kw: c.post("/api/devices/SX-PL1/places", headers=mom, json={
            "name": "X", "kind": "other", "lat": 1, "lon": 1, **kw}).status_code
        assert bad(schedule=[{"days": [1], "start": "09:00", "end": "08:00"}]) == 400      # end before start
        assert bad(schedule=[{"days": [], "start": "09:00", "end": "10:00"}]) == 400       # no day
        assert bad(schedule=[{"days": [1], "start": "9am", "end": "10:00"}]) == 400        # bad time
        assert bad(kind="spaceship") == 400

        # people: coach at swimming; teacher at school is shared with the sibling's school of the same name
        place(c, mom, "SX-PL2", "dps", "school", SCHOOL)
        r = c.post(f"/api/devices/SX-PL1/places/{swim['id']}/people", headers=mom,
                   json={"name": "Coach Ravi", "phone": "9000000102", "role": "coach"}).json()
        assert r["people"][0]["name"] == "Coach Ravi" and r["people"][0]["phone"] == "+919000000102"
        c.post(f"/api/devices/SX-PL1/places/{school['id']}/people", headers=mom,
               json={"name": "Ms Rao", "phone": "9000000103", "role": "teacher"})
        sib = next(p for p in c.get("/api/devices/SX-PL2/places", headers=mom).json() if p["kind"] == "school")
        assert [x["name"] for x in sib["people"]] == ["Ms Rao"]
        assert c.post(f"/api/devices/SX-PL1/places/{swim['id']}/people", headers=mom,
                      json={"name": "X", "phone": "9000000104", "role": "wizard"}).status_code == 400

        # edit keeps people; delete removes the place and its people
        e = c.put(f"/api/devices/SX-PL1/places/{swim['id']}", headers=mom, json={
            "name": "Aqua Swim Academy", "kind": "activity", "lat": SWIM[0], "lon": SWIM[1], "radius_m": 200,
            "schedule": [{"days": [5, 6], "start": "07:00", "end": "08:00"}]}).json()
        assert e["name"] == "Aqua Swim Academy" and e["radius_m"] == 200 and len(e["people"]) == 1
        assert c.delete(f"/api/devices/SX-PL1/places/{home['id']}", headers=mom).json()["ok"]
        assert c.delete(f"/api/devices/SX-PL1/places/{swim['id']}", headers=mom).json()["ok"]
        with SessionLocal() as db:
            assert db.query(TeacherContact).filter_by(place_id=swim["id"]).count() == 0
        other = user(c, "pl-stranger@x.com")
        assert c.get("/api/devices/SX-PL1/places", headers=other).status_code in (403, 404)


def test_schedule_alerts_late_and_left_early(monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "push", lambda users, title, body, data, **k: sent.append((title, body)))
    with TestClient(app) as c:
        mom = user(c, "pl-mom2@x.com")
        tracker(c, mom, "SX-PL3")
        day = date(2026, 11, 7)                                       # a Saturday
        swim = place(c, mom, "SX-PL3", "Swimming", "activity", SWIM,
                     schedule=[{"days": [day.weekday()], "start": "07:00", "end": "08:00"}])
        at = lambda hh, mm: datetime(day.year, day.month, day.day, hh, mm, tzinfo=ai.tz()).astimezone(timezone.utc)
        with SessionLocal() as db:
            dev = db.query(Device).filter_by(device_id="SX-PL3").one()
            dev.last_lat, dev.last_lon, dev.last_seen = HOME[0], HOME[1], at(7, 16)   # still at home
            db.commit()
            assert places.check_schedules(db, dev, now=at(7, 10)) == 0                # within the 15 min grace
            assert places.check_schedules(db, dev, now=at(7, 16)) == 1
            assert places.check_schedules(db, dev, now=at(7, 20)) == 0                # once per slot
            db.commit()
            assert any("is not at Swimming yet" in t for t, _ in sent)
            ctx = places.current_context(db, dev, now=at(7, 30))
            assert ctx["place"]["name"] == "Swimming" and ctx["until"] == "08:00" and ctx["inside"] is False
            assert places.current_context(db, dev, now=at(9, 0))["place"] is None
            # arrived, then left at 07:35 -> left early (ends 08:00); leaving at 07:55 would be fine
            g = db.get(Geofence, swim["id"])
            sent.clear()
            places.on_exit(db, dev, g, now=at(7, 35))
            places.on_exit(db, dev, g, now=at(7, 36))
            db.commit()
            assert [t for t, _ in sent].count("🚶 Babai left Swimming early") == 1
            # alerts switched off for this place -> nothing
            g.alert_late = False
            db.commit()
            day2 = at(7, 16) + timedelta(days=7)
            dev.last_seen = day2
            db.commit()
            assert places.check_schedules(db, dev, now=day2) == 0
            assert db.query(AiAlert).filter_by(device_pk=dev.id, kind="sched_late").count() == 1


def test_transport_with_and_without_beacon_and_old_bus_endpoint():
    with TestClient(app) as c:
        mom = user(c, "pl-mom3@x.com")
        dh = tracker(c, mom, "SX-PL4")
        school = place(c, mom, "SX-PL4", "School", "school", SCHOOL)
        t = c.post("/api/devices/SX-PL4/transports", headers=mom, json={
            "name": "School bus 12", "kind": "bus", "beacon_id": "bus-pl4", "driver_name": "Ramesh",
            "driver_phone": "9000000105", "place_ids": [school["id"], 999999]}).json()
        assert t[0]["beacon_id"] == "BUS-PL4" and t[0]["driver_phone"] == "+919000000105" and t[0]["place_ids"] == [school["id"]]
        # beacon link works for boarded alerts (same as the old bus feature)
        r = c.post("/api/device/telemetry", headers=dh, json={"lat": 12.97, "lon": 77.59, "ble": ["BUS-PL4"]}).json()
        assert r["cfg"]["beacons"] == ["BUS-PL4"]
        assert c.get("/api/devices/SX-PL4/transports", headers=mom).json()[0]["on_now"] is True
        auto = c.post("/api/devices/SX-PL4/transports", headers=mom, json={"name": "Auto uncle", "kind": "auto"}).json()
        assert auto[1]["beacon_id"] is None and auto[1]["kind"] == "auto"
        # removing the beacon from the bus removes the beacon link
        c.put(f"/api/devices/SX-PL4/transports/{t[0]['id']}", headers=mom, json={"name": "School bus 12", "kind": "bus"})
        with SessionLocal() as db:
            dev = db.query(Device).filter_by(device_id="SX-PL4").one()
            assert db.query(DeviceBus).filter_by(device_pk=dev.id).count() == 0 and dev.on_bus_id is None
        assert c.post("/api/devices/SX-PL4/transports", headers=mom, json={"name": "Rocket", "kind": "rocket"}).status_code == 400
        # older app: /buses still works and shows up as transport
        c.post("/api/devices/SX-PL4/buses", headers=mom, json={"name": "Van 7", "beacon_id": "VAN-PL4"})
        names = [x["name"] for x in c.get("/api/devices/SX-PL4/transports", headers=mom).json()]
        assert "Van 7" in names
        vid = next(b["id"] for b in c.get("/api/devices/SX-PL4/buses", headers=mom).json() if b["name"] == "Van 7")
        c.delete(f"/api/devices/SX-PL4/buses/{vid}", headers=mom)
        assert "Van 7" not in [x["name"] for x in c.get("/api/devices/SX-PL4/transports", headers=mom).json()]
        for x in c.get("/api/devices/SX-PL4/transports", headers=mom).json():
            c.delete(f"/api/devices/SX-PL4/transports/{x['id']}", headers=mom)
        assert c.get("/api/devices/SX-PL4/transports", headers=mom).json() == []


def test_emergency_goes_only_to_the_chosen_place():
    with TestClient(app) as c:
        mom = user(c, "pl-mom4@x.com", "9000000110")
        c.post("/api/admin/users/plan", headers=A, json={"email": "pl-mom4@x.com", "plan": "smart"})
        dh = tracker(c, mom, "SX-PL5")
        school = place(c, mom, "SX-PL5", "School", "school", SCHOOL)
        swim = place(c, mom, "SX-PL5", "Swimming", "activity", SWIM)
        c.post(f"/api/devices/SX-PL5/places/{school['id']}/people", headers=mom,
               json={"name": "Teacher", "phone": "9000000111", "role": "teacher"})
        c.post(f"/api/devices/SX-PL5/places/{swim['id']}/people", headers=mom,
               json={"name": "Coach", "phone": "9000000112", "role": "coach"})
        teacher, coach = user(c, "pl-teacher@x.com", "9000000111"), user(c, "pl-coach@x.com", "9000000112")
        board = lambda h: c.get("/api/staff/board", headers=h).json()["children"]

        c.post("/api/device/telemetry", headers=dh, json={"lat": SWIM[0], "lon": SWIM[1], "sos": 1})   # buzzer
        assert board(teacher)[0]["sos"] is None and board(coach)[0]["sos"] is None
        assert board(coach)[0]["school"] == "Swimming" and board(coach)[0]["my_role"] == "coach"
        r = c.post("/api/devices/SX-PL5/emergency", headers=mom, json={"target": "place", "place_id": swim["id"]}).json()
        assert r["people"] == 1 and r["place"] == "Swimming" and r["already"] is False
        assert board(coach)[0]["sos"] is not None                    # coach sees it …
        assert board(teacher)[0]["sos"] is None                      # … the school does not
        sid = board(coach)[0]["sos"]["sos_id"]
        assert c.get(f"/api/staff/sos/{sid}/track", headers=coach).status_code == 200
        assert c.get(f"/api/staff/sos/{sid}/track", headers=teacher).status_code == 404
        # Emergency – School alerts only school people (not the coach again) and now the teacher sees it
        r = c.post("/api/devices/SX-PL5/emergency", headers=mom, json={"target": "school"}).json()
        assert r["contacts"] == 1 and r["already"] is False
        assert board(teacher)[0]["sos"] is not None
        assert c.post("/api/devices/SX-PL5/emergency", headers=mom, json={"target": "place", "place_id": school["id"] + 99999}).status_code == 400


def test_migration_of_older_data():
    with TestClient(app) as c:
        mom = user(c, "pl-mom5@x.com")
        tracker(c, mom, "SX-PL6")
        c.post("/api/devices/SX-PL6/geofences", headers=mom, json={"name": "Maths Tuition", "lat": 1.0, "lon": 1.0})
        c.post("/api/devices/SX-PL6/geofences", headers=mom, json={"name": "St. Mary's School", "lat": 2.0, "lon": 2.0})
        c.post("/api/devices/SX-PL6/teacher-contacts", headers=mom, json={"name": "Old teacher", "phone": "9000000120"})
        with SessionLocal() as db:
            dev = db.query(Device).filter_by(device_id="SX-PL6").one()
            kinds = {g.name: g.kind for g in db.query(Geofence).filter_by(device_pk=dev.id)}
            assert kinds == {"Maths Tuition": "class", "St. Mary's School": "school"}
            assert db.query(TeacherContact).filter_by(device_pk=dev.id).one().place_id is None
            places.migrate(db)
            places.migrate(db)                                        # idempotent
            school = db.query(Geofence).filter_by(device_pk=dev.id, kind="school").one()
            assert db.query(TeacherContact).filter_by(device_pk=dev.id).one().place_id == school.id
