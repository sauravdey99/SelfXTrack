"""Phase 6: production settings check, rate limit, security headers, export + delete account, retention, pages."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.config import Settings, production_problems
from app.db import SessionLocal
from app.main import app
from app.models import Device, Location
from app.routers import privacy


def test_phase6(monkeypatch):
    assert len(production_problems(Settings())) >= 5           # dev defaults are flagged
    good = Settings(jwt_secret="x" * 40, admin_key="y" * 30, otp_dev_mode=False, sms_provider="msg91",
                    default_plan="basic", database_url="postgresql+psycopg://a@b/c", cors_origins="https://selfxtrack.in",
                    public_base_url="https://api.selfxtrack.in")
    assert production_problems(good) == []
    with TestClient(app) as c:
        r = c.post("/api/auth/register", json={"email": "p6@x.com", "name": "P", "password": "secret123", "consent": False})
        assert r.status_code == 400
        h = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": "p6@x.com", "name": "P",
                                                                            "password": "secret123"}).json()["access_token"]}
        prov = c.post("/api/admin/devices", json={"device_id": "SX-P6"}, headers={"X-Admin-Key": "test-admin"}).json()
        c.post("/api/devices/claim", headers=h, json={"device_id": "SX-P6", "claim_code": prov["claim_code"], "name": "Kid"})
        dh = {"X-Device-Id": "SX-P6", "X-Device-Secret": prov["device_secret"]}
        r = c.post("/api/device/telemetry", headers=dh, json={"lat": 12.9, "lon": 77.5})
        assert r.headers["x-content-type-options"] == "nosniff"

        ex = c.get("/api/me/export", headers=h).json()
        assert ex["account"]["consent_at"] and ex["devices"][0]["locations_30d"][0]["lat"] == 12.9

        # retention: an old point is removed, the new one stays
        with SessionLocal() as db:
            d = db.query(Device).filter_by(device_id="SX-P6").one()
            db.add(Location(device_pk=d.id, ts=datetime.now(timezone.utc) - timedelta(days=400), lat=1, lon=1))
            db.commit()
            assert privacy.cleanup(db)["locations"] >= 1
            assert db.query(Location).filter_by(device_pk=d.id).count() == 1

        assert c.request("DELETE", "/api/me", headers=h, json={"password": "wrong"}).status_code == 403
        assert c.request("DELETE", "/api/me", headers=h, json={"password": "secret123"}).json()["ok"]
        assert c.get("/api/devices", headers=h).status_code == 401                # token no longer works
        with SessionLocal() as db:
            d = db.query(Device).filter_by(device_id="SX-P6").one()
            assert d.claimed is False and db.query(Location).filter_by(device_pk=d.id).count() == 0

        assert "Privacy Policy" in c.get("/privacy").text and "Terms" in c.get("/terms").text

        # rate limit on login (30/min per IP in production; tests set it explicitly)
        from app.config import settings
        monkeypatch.setattr(settings, "rate_limit_per_minute", 30)
        codes = [c.post("/api/auth/login", json={"email": "nobody@x.com", "password": "nopenope"}).status_code
                 for _ in range(35)]
        assert 429 in codes
