"""Live map: history?today=true returns only today's path (from local midnight)."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Device, Location

A = {"X-Admin-Key": "test-admin"}


def test_history_today_only():
    with TestClient(app) as c:
        h = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": "ht@x.com", "name": "ht",
                                                                            "password": "secret123"}).json()["access_token"]}
        prov = c.post("/api/admin/devices", json={"device_id": "SX-HT"}, headers=A).json()
        c.post("/api/devices/claim", headers=h, json={"device_id": "SX-HT", "claim_code": prov["claim_code"], "name": "Kid"})
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            dev = db.query(Device).filter_by(device_id="SX-HT").one()
            db.add_all([Location(device_pk=dev.id, ts=now - timedelta(hours=30), lat=12.9, lon=77.6),
                        Location(device_pk=dev.id, ts=now, lat=12.91, lon=77.61)])
            db.commit()
        assert len(c.get("/api/devices/SX-HT/history?hours=48", headers=h).json()) == 2
        today = c.get("/api/devices/SX-HT/history?today=true", headers=h).json()
        assert [p["lat"] for p in today] == [12.91]
