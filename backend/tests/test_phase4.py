from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Device, Location


def H(c, email):
    return {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": email, "name": "Mom",
                                                                          "password": "secret123"}).json()["access_token"]}


ROUTE = [(12.9716, 77.5946), (12.9730, 77.5960), (12.9745, 77.5975), (12.9760, 77.5990)]   # home -> school


def test_ai_and_billing():
    with TestClient(app) as c:
        A = {"X-Admin-Key": "test-admin"}
        prov = c.post("/api/admin/devices", json={"device_id": "SX-P4"}, headers=A).json()
        mom = H(c, "mom4@example.com")
        c.post("/api/devices/claim", headers=mom, json={"device_id": "SX-P4", "claim_code": prov["claim_code"], "name": "Riya"})
        c.put("/api/devices/SX-P4/setup", headers=mom, json={"public_holidays": False})   # synthetic dates
        c.post("/api/devices/SX-P4/geofences", headers=mom, json={"name": "Home", "lat": 12.9716, "lon": 77.5946, "radius_m": 100})

        # 7 days of the same routine: home 07:00-07:30, walk, school 08:00-08:40
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            dev = db.query(Device).filter_by(device_id="SX-P4").one()
            for d in range(1, 8):
                t = (now - timedelta(days=d)).replace(hour=1, minute=30, second=0, microsecond=0)   # 07:00 IST
                for k in range(4):
                    db.add(Location(device_pk=dev.id, ts=t + timedelta(minutes=10 * k), lat=ROUTE[0][0], lon=ROUTE[0][1], speed=0))
                for i, (la, lo) in enumerate(ROUTE[1:], 1):
                    db.add(Location(device_pk=dev.id, ts=t + timedelta(minutes=30 + 5 * i), lat=la, lon=lo, speed=5))
                for k in range(5):
                    db.add(Location(device_pk=dev.id, ts=t + timedelta(minutes=50 + 10 * k), lat=ROUTE[-1][0], lon=ROUTE[-1][1], speed=0))
            db.commit()

        # Basic: locked
        c.post("/api/admin/users/plan", headers=A, json={"email": "mom4@example.com", "plan": "basic"})
        assert c.get("/api/devices/SX-P4/insights", headers=mom).json()["locked"] is True
        assert c.post("/api/devices/SX-P4/ask", headers=mom, json={"question": "where?"}).status_code == 402

        # Billing (dev mode) -> Smart
        r = c.post("/api/billing/subscribe", headers=mom, json={"plan": "smart", "period": "monthly"}).json()
        assert r["mode"] == "dev" and r["amount_inr"] == 299
        b = c.post(f"/api/billing/dev-confirm/{r['payment_id']}", headers=mom).json()
        assert b["plan"] == "smart" and b["status"] == "active"

        ins = c.post("/api/devices/SX-P4/learn", headers=mom).json()
        assert ins["days"] == 7 and ins["places"][0]["name"] in ("Home", "Frequent place 1", "Frequent place 2")
        assert any(p["name"] == "Home" for p in ins["places"])

        # unusual route: 2 reports ~1.5 km off the corridor -> advisory alert (not SOS)
        dh = {"X-Device-Id": "SX-P4", "X-Device-Secret": prov["device_secret"]}
        c.post("/api/device/telemetry", headers=dh, json={"lat": 12.9716, "lon": 77.5946})
        c.post("/api/device/telemetry", headers=dh, json={"lat": 12.9900, "lon": 77.6100, "spd": 12})
        r = c.post("/api/device/telemetry", headers=dh, json={"lat": 12.9905, "lon": 77.6105, "spd": 12}).json()
        assert r["sos_active"] is False
        ins = c.get("/api/devices/SX-P4/insights", headers=mom).json()
        assert ins["ready"] and any(a["kind"] == "route" for a in ins["alerts"])
        assert ins["eta"] is not None

        yday = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30) - timedelta(days=1)).date().isoformat()
        s = c.get(f"/api/devices/SX-P4/summary?day={yday}", headers=mom).json()
        assert s["text"].startswith("Normal day") and "Home" in s["text"]
        a = c.post("/api/devices/SX-P4/ask", headers=mom, json={"question": "Where was Riya yesterday at 7:10 am?"}).json()
        assert "Home" in a["answer"]

        # Guardian-only incident report
        c.post("/api/device/telemetry", headers=dh, json={"lat": 12.9905, "lon": 77.6105, "sos": 1})
        sos_id = c.get("/api/sos", headers=mom).json()[0]["id"]
        assert c.get(f"/api/sos/{sos_id}/report", headers=mom).status_code == 402
        c.post("/api/admin/users/plan", headers=A, json={"email": "mom4@example.com", "plan": "guardian"})
        rep = c.get(f"/api/sos/{sos_id}/report", headers=mom).json()
        assert "SOS started" in rep["text"]

        # expired + grace -> back to basic, SOS still works
        with SessionLocal() as db:
            from app.models import User
            u = db.query(User).filter_by(email="mom4@example.com").one()
            u.plan_expires_at = datetime.now(timezone.utc) - timedelta(days=8)
            db.commit()
        assert c.get("/api/billing/me", headers=mom).json()["plan"] == "basic"
        assert c.get("/api/sos", headers=mom).status_code == 200
