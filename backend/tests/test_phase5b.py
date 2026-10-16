"""Phase 5: elderly fall + inactivity, BLE bus, OTA, admin API, school web page."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import notify
from app.db import SessionLocal
from app.main import app
from app.models import Device, SosEvent
from app.services_p5 import check_inactivity

A = {"X-Admin-Key": "test-admin"}


def test_phase5b(monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "push", lambda users, title, body, data, **k: sent.append((title, body)))
    with TestClient(app) as c:
        h = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": "p5b@x.com", "name": "P",
                                                                            "password": "secret123"}).json()["access_token"]}
        c.post("/api/admin/users/plan", headers=A, json={"email": "p5b@x.com", "plan": "guardian"})

        # ---- elderly: fall -> SOS (reason fall)
        prov = c.post("/api/admin/devices", json={"device_id": "SX-OLD", "kind": "elderly"}, headers=A).json()
        c.post("/api/devices/claim", headers=h, json={"device_id": "SX-OLD", "claim_code": prov["claim_code"],
                                                      "name": "Dadi", "kind": "elderly"})
        dh = {"X-Device-Id": "SX-OLD", "X-Device-Secret": prov["device_secret"]}
        r = c.post("/api/device/telemetry", headers=dh, json={"lat": 12.97, "lon": 77.59, "act": 5, "fw": "1.1.0"}).json()
        assert r["cfg"]["fall"] is True and r["ota"] is None
        sent.clear()
        r = c.post("/api/device/telemetry", headers=dh, json={"lat": 12.97, "lon": 77.59, "fall": 1}).json()
        assert r["sos_active"] is True and any("FALL" in t for t, _ in sent)
        with SessionLocal() as db:
            ev = db.query(SosEvent).order_by(SosEvent.id.desc()).first()
            assert ev.source == "fall"
        sos_id = c.get("/api/sos", headers=h).json()[0]["id"]
        c.post(f"/api/sos/{sos_id}/resolve", headers=h)

        # care settings + inactivity
        care = c.put("/api/devices/SX-OLD/care", headers=h, json={"inactivity_hours": 2, "active_from": "00:00",
                                                                  "active_to": "23:59"}).json()
        assert care["inactivity_hours"] == 2
        with SessionLocal() as db:
            d = db.query(Device).filter_by(device_id="SX-OLD").one()
            d.last_active_at = datetime.now(timezone.utc) - timedelta(hours=3)
            d.last_seen = datetime.now(timezone.utc)
            db.commit()
            sent.clear()
            assert check_inactivity(db) == 1 and check_inactivity(db) == 0
        assert any("Check on Dadi" in t for t, _ in sent)

        # ---- BLE bus
        prov2 = c.post("/api/admin/devices", json={"device_id": "SX-BUS"}, headers=A).json()
        c.post("/api/devices/claim", headers=h, json={"device_id": "SX-BUS", "claim_code": prov2["claim_code"], "name": "Riya"})
        buses = c.post("/api/devices/SX-BUS/buses", headers=h, json={"name": "Bus 12", "beacon_id": "bus-12"}).json()
        assert buses[0]["beacon_id"] == "BUS-12"
        bh = {"X-Device-Id": "SX-BUS", "X-Device-Secret": prov2["device_secret"]}
        sent.clear()
        r = c.post("/api/device/telemetry", headers=bh, json={"lat": 12.97, "lon": 77.59, "ble": ["BUS-12"]}).json()
        assert r["cfg"]["beacons"] == ["BUS-12"] and any("on the bus" in t for t, _ in sent)
        c.post("/api/device/telemetry", headers=bh, json={"lat": 12.98, "lon": 77.60, "ble": []})
        sent.clear()
        c.post("/api/device/telemetry", headers=bh, json={"lat": 12.98, "lon": 77.60, "ble": []})
        assert any("got off" in t for t, _ in sent)
        ev = c.get("/api/devices/SX-BUS/bus-events", headers=h).json()
        assert [e["kind"] for e in ev] == ["alight", "board"]

        # ---- OTA: upload -> offered -> download -> status
        img = bytes([0xE9]) + b"\x00" * 4095
        rel = c.post("/api/admin/firmware?version=1.2.0&notes=test", headers={**A, "Content-Type": "application/octet-stream"},
                     content=img).json()
        assert rel["size"] == 4096
        assert c.post("/api/admin/firmware?version=9.9", headers=A, content=b"x" * 2000).status_code == 400   # bad magic
        r = c.post("/api/device/telemetry", headers=bh, json={"lat": 12.98, "lon": 77.60, "bat": 80, "fw": "1.1.0"}).json()
        assert r["ota"]["version"] == "1.2.0"
        fid = r["ota"]["url"].rsplit("/", 1)[1]
        assert c.get(f"/api/device/firmware/{fid}", headers=bh).content == img
        c.post("/api/device/ota-status", headers=bh, json={"version": "1.2.0", "status": "installed"})
        r = c.post("/api/device/telemetry", headers=bh, json={"lat": 12.98, "lon": 77.60, "bat": 80, "fw": "1.2.0"}).json()
        assert r["ota"] is None
        r = c.post("/api/device/telemetry", headers=bh, json={"bat": 10, "fw": "1.1.0"}).json()
        assert r["ota"] is None                                        # low battery -> no update

        # ---- admin API + web pages
        assert c.get("/api/admin/overview").status_code in (401, 403, 422)
        o = c.get("/api/admin/overview", headers=A).json()
        assert o["devices"] >= 2 and "guardian" in o["plans"]
        assert any(d["device_id"] == "SX-BUS" and d["ota_status"] == "1.2.0: installed" for d in c.get("/api/admin/devices", headers=A).json())
        assert c.get("/school").status_code == 200 and "School safety dashboard" in c.get("/school").text
        assert c.get("/admin").status_code == 200
