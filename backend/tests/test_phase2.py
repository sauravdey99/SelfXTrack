from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Device
from app.services import check_offline


def setup(c: TestClient, did: str, email: str):
    prov = c.post("/api/admin/devices", json={"device_id": did}, headers={"X-Admin-Key": "test-admin"}).json()
    tok = c.post("/api/auth/register", json={"email": email, "name": "P", "password": "secret123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    c.post("/api/devices/claim", headers=h, json={"device_id": did, "claim_code": prov["claim_code"], "name": "Kid"})
    return h, {"X-Device-Id": did, "X-Device-Secret": prov["device_secret"]}


def test_geofence_offline_share_school():
    with TestClient(app) as c:
        h, dh = setup(c, "SX-P2", "p2@example.com")
        # safe zone around school
        g = c.post("/api/devices/SX-P2/geofences", headers=h,
                   json={"name": "School", "lat": 12.9800, "lon": 77.6000, "radius_m": 200}).json()
        c.post("/api/device/telemetry", headers=dh, json={"lat": 12.9700, "lon": 77.5900, "acc": 10})  # outside
        assert c.get("/api/devices/SX-P2/geofences", headers=h).json()[0]["inside"] is False
        tok = h["Authorization"].split()[1]
        with c.websocket_connect(f"/ws?token={tok}") as ws:
            c.post("/api/device/telemetry", headers=dh, json={"lat": 12.9801, "lon": 77.6001, "acc": 10})
            types = {ws.receive_json()["type"], ws.receive_json()["type"]}
            assert "geofence_enter" in types
        assert c.delete(f"/api/devices/SX-P2/geofences/{g['id']}", headers=h).json()["ok"]

        # offline alert
        with SessionLocal() as db:
            d = db.query(Device).filter_by(device_id="SX-P2").one()
            d.last_seen = datetime.now(timezone.utc) - timedelta(hours=2)
            db.commit()
            assert check_offline(db) >= 1
            assert db.query(Device).filter_by(device_id="SX-P2").one().offline_notified
        c.post("/api/device/telemetry", headers=dh, json={"bat": 50})
        with SessionLocal() as db:
            assert not db.query(Device).filter_by(device_id="SX-P2").one().offline_notified

        # school circle: admin creates school, teacher joins, parent links child
        admin = {"Authorization": "Bearer " + c.post("/api/auth/register", json={
            "email": "principal@example.com", "name": "Principal", "password": "secret123"}).json()["access_token"]}
        school = c.post("/api/schools", headers=admin, json={"name": "Green Valley School"}).json()
        teacher = {"Authorization": "Bearer " + c.post("/api/auth/register", json={
            "email": "teacher@example.com", "name": "Teacher", "password": "secret123"}).json()["access_token"]}
        assert c.post("/api/schools/join", headers=teacher, json={"staff_code": school["staff_code"]}).status_code == 400
        code = c.post("/api/auth/otp/request", headers=teacher, json={"phone": "9876543210"}).json()["dev_code"]
        assert c.post("/api/auth/otp/verify", headers=teacher, json={"phone": "9876543210", "code": "000000" if code != "000000" else "111111"}).status_code == 400
        assert c.post("/api/auth/otp/verify", headers=teacher, json={"phone": "9876543210", "code": code}).json()["phone_verified"]
        j = c.post("/api/schools/join", headers=teacher, json={"staff_code": school["staff_code"]}).json()
        assert j["status"] == "pending"
        staff = c.get(f"/api/schools/{school['id']}/staff", headers=admin).json()
        assert {x["status"] for x in staff} == {"approved", "pending"}
        tid = [x for x in staff if x["status"] == "pending"][0]["user_id"]
        assert c.get(f"/api/schools/{school['id']}/sos", headers=teacher).status_code == 403
        assert c.post(f"/api/schools/{school['id']}/staff/{tid}/approve", headers=admin).json()["status"] == "approved"
        assert c.post("/api/devices/SX-P2/school", headers=h,
                      json={"parent_code": school["parent_code"], "class_name": "5A"}).status_code == 200
        # no SOS -> teacher sees nothing (privacy)
        assert c.get(f"/api/schools/{school['id']}/sos", headers=teacher).json() == []

        # SOS + live link
        c.post("/api/device/telemetry", headers=dh, json={"lat": 12.98, "lon": 77.60, "spd": 22, "hdg": 45, "sos": 1})
        # buzzer alone -> family only; the school does not see it
        assert c.get(f"/api/schools/{school['id']}/sos", headers=teacher).json() == []
        assert c.post("/api/devices/SX-P2/emergency", headers=h, json={"target": "school"}).json()["staff"] >= 1
        sos = c.get(f"/api/schools/{school['id']}/sos", headers=teacher).json()
        assert len(sos) == 1 and sos[0]["class_name"] == "5A" and sos[0]["speed_kmh"] == 22 and sos[0]["school_alerted"]
        r = c.post(f"/api/schools/{school['id']}/sos/{sos[0]['sos_id']}/group", headers=teacher)
        assert r.status_code == 403          # only the parent can start Emergency – Group
        link = c.post("/api/devices/SX-P2/share-links", headers=h, json={"minutes": 30, "for_sos": True}).json()
        data = c.get(f"/api/live/{link['token']}").json()
        assert data["sos_active"] and data["lat"] == 12.98
        assert "Leaflet" in c.get(f"/live/{link['token']}").text or "leaflet" in c.get(f"/live/{link['token']}").text
        # teacher can acknowledge, cannot resolve
        assert c.post(f"/api/sos/{sos[0]['sos_id']}/acknowledge", headers=teacher).status_code in (200,)
        assert c.post(f"/api/sos/{sos[0]['sos_id']}/resolve", headers=teacher).status_code == 404
        # family resolves -> SOS link stops automatically
        assert c.post(f"/api/sos/{sos[0]['sos_id']}/resolve", headers=h).status_code == 200
        assert c.get(f"/api/live/{link['token']}").status_code == 410
