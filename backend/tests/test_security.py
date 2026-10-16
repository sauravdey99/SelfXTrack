"""Security fixes: live-link page injection, OTP purpose, password length, spoofed X-Forwarded-For, admin key."""
from fastapi.testclient import TestClient

from app.main import app

A = {"X-Admin-Key": "test-admin"}


def test_live_page_rejects_injection_and_sets_csp():
    with TestClient(app) as c:
        bad = c.get("/live/x');alert(1);//")
        assert bad.status_code == 404 and "alert(1)" not in bad.text
        ok = c.get("/live/" + "A" * 22)                          # well-formed (unknown) token -> page, safely embedded
        assert ok.status_code == 200 and 'const TOKEN="' + "A" * 22 + '"' in ok.text
        assert "default-src 'none'" in ok.headers["content-security-policy"]
        assert "innerHTML" not in ok.text and 'integrity="sha256-' in ok.text


def test_device_name_shown_as_text_not_html():
    with TestClient(app) as c:
        prov = c.post("/api/admin/devices", json={"device_id": "SX-XSS"}, headers=A).json()
        h = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": "xss@x.com", "name": "X",
                                                                            "password": "secret123"}).json()["access_token"]}
        c.post("/api/devices/claim", headers=h, json={"device_id": "SX-XSS", "claim_code": prov["claim_code"],
                                                      "name": "<img src=x onerror=alert(1)>"})
        link = c.post("/api/devices/SX-XSS/share-links", headers=h, json={"minutes": 30}).json()
        page = c.get(f"/live/{link['token']}").text
        assert "textContent" in page and "<img src=x" not in page    # name only arrives as JSON data, set via textContent


def test_reset_needs_reset_code_and_8_chars():
    with TestClient(app) as c:
        h = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": "rs@x.com", "name": "R",
                                                                            "password": "secret123"}).json()["access_token"]}
        assert c.post("/api/auth/register", json={"email": "short@x.com", "name": "S", "password": "abc12"}).status_code == 422
        code = c.post("/api/auth/otp/request", headers=h, json={"phone": "9000000077"}).json()["dev_code"]
        c.post("/api/auth/otp/verify", headers=h, json={"phone": "9000000077", "code": code})
        verify_code = c.post("/api/auth/otp/request", headers=h, json={"phone": "9000000077"}).json()["dev_code"]
        # a phone-verification code must not reset the password
        r = c.post("/api/auth/password/reset", json={"email": "rs@x.com", "code": verify_code, "new_password": "newpass123"})
        assert r.status_code == 400
        reset = c.post("/api/auth/password/forgot", json={"email": "rs@x.com"}).json()["dev_code"]
        assert c.post("/api/auth/password/reset", json={"email": "rs@x.com", "code": reset,
                                                         "new_password": "short"}).status_code == 400
        assert c.post("/api/auth/password/reset", json={"email": "rs@x.com", "code": reset,
                                                         "new_password": "newpass123"}).json()["ok"] is True


def test_fake_forwarded_for_does_not_bypass_rate_limit(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "rate_limit_per_minute", 5)
    with TestClient(app) as c:
        codes = [c.post("/api/auth/login", headers={"X-Forwarded-For": f"10.0.0.{i}"},
                        json={"email": "nobody@x.com", "password": "wrongpass1"}).status_code
                 for i in range(settings.rate_limit_per_minute + 2)]
        assert 429 in codes                                        # different fake IPs, still limited


def test_admin_key_required():
    with TestClient(app) as c:
        assert c.get("/api/admin/overview", headers={"X-Admin-Key": "wrong"}).status_code == 403
        assert c.get("/api/admin/overview", headers=A).status_code == 200
