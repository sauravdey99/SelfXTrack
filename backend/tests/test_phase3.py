from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import SosEvent
from app.services_help import check_escalations


def user(c, email, phone=None):
    h = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": email, "name": email.split("@")[0],
                                                                        "password": "secret123"}).json()["access_token"]}
    if phone:
        code = c.post("/api/auth/otp/request", headers=h, json={"phone": phone}).json()["dev_code"]
        c.post("/api/auth/otp/verify", headers=h, json={"phone": phone, "code": code})
    return h


def test_group_school_plans_password():
    with TestClient(app) as c:
        prov = c.post("/api/admin/devices", json={"device_id": "SX-P3"}, headers={"X-Admin-Key": "test-admin"}).json()
        mom = user(c, "mom3@example.com", "9000000001")
        c.post("/api/devices/claim", headers=mom, json={"device_id": "SX-P3", "claim_code": prov["claim_code"], "name": "Riya"})
        dh = {"X-Device-Id": "SX-P3", "X-Device-Secret": prov["device_secret"]}
        c.post("/api/device/telemetry", headers=dh, json={"lat": 12.9716, "lon": 77.5946})

        # helpers: near (300 m), far (1.5 km), unverified near
        near = user(c, "near@example.com", "9000000002")
        far = user(c, "far@example.com", "9000000003")
        anon = user(c, "anon@example.com")
        c.post("/api/helpers/location", headers=near, json={"lat": 12.9743, "lon": 77.5946})
        c.post("/api/helpers/location", headers=far, json={"lat": 12.9851, "lon": 77.5946})
        c.post("/api/helpers/location", headers=anon, json={"lat": 12.9720, "lon": 77.5946})

        # manual teacher contact
        assert c.post("/api/devices/SX-P3/teacher-contacts", headers=mom,
                      json={"name": "Class teacher", "phone": "9000000009"}).status_code == 200

        # child setup: manual school + rename
        st = c.put("/api/devices/SX-P3/setup", headers=mom, json={"manual_school": "St. Mary's", "manual_class": "5A"}).json()
        assert st["manual_school"] == "St. Mary's" and st["contacts"] == 1 and st["family"][0]["role"] == "owner"

        # family invite by mobile -> grandma registers + verifies -> parent accepts
        st = c.post("/api/devices/SX-P3/family-invites", headers=mom, json={"name": "Grandma", "phone": "9000000020"}).json()
        assert st["invites"][0]["ready"] is False
        gm = user(c, "gm@example.com", "9000000020")
        iid = c.get("/api/devices/SX-P3/setup", headers=mom).json()["invites"][0]["id"]
        st = c.post(f"/api/devices/SX-P3/family-invites/{iid}/accept", headers=mom).json()
        assert st["invites"] == [] and len(st["family"]) == 2
        assert c.get("/api/devices", headers=gm).json()[0]["device_id"] == "SX-P3"

        # 2nd child: family auto-shared, choose the same school -> staff copied; new staff added to both
        prov2 = c.post("/api/admin/devices", json={"device_id": "SX-P3B"}, headers={"X-Admin-Key": "test-admin"}).json()
        c.post("/api/devices/claim", headers=mom, json={"device_id": "SX-P3B", "claim_code": prov2["claim_code"], "name": "Rohan"})
        assert len(c.get("/api/devices", headers=gm).json()) == 2
        c.post("/api/devices/SX-P3/family-invites", headers=mom, json={"name": "Uncle", "phone": "9000000040"})
        assert c.get("/api/devices/SX-P3B/setup", headers=mom).json()["invites"][0]["name"] == "Uncle"
        assert c.get("/api/my-schools", headers=mom).json()[0]["name"] == "St. Mary's"
        st2 = c.put("/api/devices/SX-P3B/setup", headers=mom, json={"manual_school": "st. mary's", "manual_class": "2B"}).json()
        assert st2["contacts"] == 1
        c.post("/api/devices/SX-P3B/teacher-contacts", headers=mom, json={"name": "Guard", "phone": "9000000030", "role": "staff"})
        assert len(c.get("/api/devices/SX-P3/teacher-contacts", headers=mom).json()) == 2

        # Basic plan blocks school/group
        c.post("/api/admin/users/plan", headers={"X-Admin-Key": "test-admin"}, json={"email": "mom3@example.com", "plan": "basic"})
        assert c.post("/api/devices/SX-P3/emergency", headers=mom, json={"target": "group"}).status_code == 402
        c.post("/api/admin/users/plan", headers={"X-Admin-Key": "test-admin"}, json={"email": "mom3@example.com", "plan": "smart"})

        # parent escalates after a safe-zone exit (no device SOS) -> group: only verified near helper
        r = c.post("/api/devices/SX-P3/emergency", headers=mom, json={"target": "group"}).json()
        assert r["notified"] == 1 and r["radius_m"] == 1000
        sos_id, help_id = r["sos_id"], r["help_id"]

        # teacher whose number the parent added sees the child on the school dashboard (no codes)
        teacher = user(c, "teacher3@example.com", "9000000009")
        board = c.get("/api/staff/board", headers=teacher).json()["children"]
        assert board[0]["name"] == "Riya" and board[0]["sos"] is None          # group help alone: school not alerted
        assert c.get(f"/api/staff/sos/{sos_id}/track", headers=teacher).status_code == 404
        # parent presses Emergency – School -> staff + both manual teacher contacts alerted, child appears on the board
        assert c.post("/api/devices/SX-P3/emergency", headers=mom, json={"target": "school"}).json()["contacts"] == 2
        board = c.get("/api/staff/board", headers=teacher).json()["children"]
        assert board[0]["name"] == "Riya" and board[0]["school"] == "St. Mary's" and board[0]["sos"]["sos_id"] == sos_id
        assert board[0]["sos"]["group_allowed"] is False      # smart plan
        assert board[0]["parents"][0]["phone"] == "+919000000001" and board[0]["parents"][0]["raised"] is True
        assert c.get(f"/api/staff/sos/{sos_id}/track", headers=teacher).json()["lat"] == 12.9716
        assert c.post(f"/api/staff/sos/{sos_id}/group", headers=teacher).status_code == 403   # parent only
        assert c.get("/api/staff/board", headers=far).json()["children"] == []
        lvl1 = c.get(f"/api/help/{help_id}", headers=near).json()
        assert "lat" not in lvl1 and lvl1["distance_m"] == 300        # Level 1: no exact location
        assert c.get(f"/api/help/{help_id}", headers=far).status_code == 404

        # widen to 2 km after timeout
        with SessionLocal() as db:
            from app.models import HelpRequest
            hr = db.get(HelpRequest, help_id)
            hr.created_at = datetime.now(timezone.utc) - timedelta(minutes=5)
            db.commit()
            check_escalations(db)
        assert c.get(f"/api/help/{help_id}", headers=far).status_code == 200

        acc = c.post(f"/api/help/{help_id}/accept", headers=near).json()
        assert acc["lat"] == 12.9716 and "safety" in acc               # Level 2 after accepting
        st = c.get(f"/api/sos/{sos_id}/status", headers=mom).json()
        assert st["group"]["notified"] == 2 and st["helpers"][0]["name"] == "near"
        assert any(l["kind"] == "helper" for l in st["access_log"])

        # pressing Emergency – School again does not alert the school twice
        assert c.post("/api/devices/SX-P3/emergency", headers=mom, json={"target": "school"}).json().get("already") is True

        # resolve -> helper access ends
        c.post(f"/api/sos/{sos_id}/resolve", headers=mom)
        assert c.get(f"/api/help/{help_id}", headers=near).json()["closed"]

        # device SOS auto-escalates to school after 300 s if no parent responds
        c.post("/api/device/telemetry", headers=dh, json={"sos": 1})
        with SessionLocal() as db:
            ev = db.query(SosEvent).filter_by(status="active").order_by(SosEvent.id.desc()).first()
            ev.started_at = datetime.now(timezone.utc) - timedelta(seconds=301)
            db.commit()
            check_escalations(db)
            assert db.get(SosEvent, ev.id).school_notified_at is not None

        # forgot password via OTP
        f = c.post("/api/auth/password/forgot", json={"email": "mom3@example.com"}).json()
        assert c.post("/api/auth/password/reset", json={"email": "mom3@example.com", "code": f["dev_code"],
                                                        "new_password": "newpass123"}).json()["ok"]
        assert c.post("/api/auth/login", json={"email": "mom3@example.com", "password": "newpass123"}).status_code == 200
        assert c.post("/api/auth/logout", headers=mom).json()["ok"]
