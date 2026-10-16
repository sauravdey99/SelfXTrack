import os
import tempfile

_DB = os.path.join(tempfile.mkdtemp(), "test_selfx.db")
os.environ["SELFX_DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["SELFX_ADMIN_KEY"] = "test-admin"

import pytest
from fastapi.testclient import TestClient

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _user(client, email):
    r = client.post("/api/auth/register", json={"email": email, "name": "Parent", "password": "secret123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_full_flow(client):
    # factory provisions a device
    r = client.post("/api/admin/devices", json={"device_id": "SX-0001"}, headers={"X-Admin-Key": "test-admin"})
    assert r.status_code == 200
    prov = r.json()
    dev_h = {"X-Device-Id": "SX-0001", "X-Device-Secret": prov["device_secret"]}

    parent = _user(client, "mom@example.com")
    r = client.post("/api/devices/claim", headers=parent,
                    json={"device_id": "SX-0001", "claim_code": prov["claim_code"], "name": "Riya"})
    assert r.status_code == 200, r.text

    # wrong secret rejected
    r = client.post("/api/device/telemetry", json={"lat": 1, "lon": 1},
                    headers={"X-Device-Id": "SX-0001", "X-Device-Secret": "bad"})
    assert r.status_code == 401

    # normal location
    r = client.post("/api/device/telemetry", headers=dev_h,
                    json={"lat": 12.9716, "lon": 77.5946, "acc": 8, "spd": 3, "bat": 80})
    assert r.status_code == 200 and r.json()["interval_s"] == 300 and not r.json()["sos_active"]

    # websocket receives SOS
    token = parent["Authorization"].split()[1]
    with client.websocket_connect(f"/ws?token={token}") as ws:
        r = client.post("/api/device/telemetry", headers=dev_h,
                        json={"lat": 12.9720, "lon": 77.5950, "spd": 18, "bat": 79, "sos": 1})
        assert r.json()["sos_active"] and r.json()["interval_s"] == 10
        msgs = [ws.receive_json(), ws.receive_json()]
        assert {m["type"] for m in msgs} == {"location", "sos"}

    d = client.get("/api/devices", headers=parent).json()[0]
    assert d["name"] == "Riya" and d["online"] and d["active_sos"]
    sos = client.get("/api/sos", headers=parent).json()
    assert len(sos) == 1 and sos[0]["status"] == "active"
    assert client.post(f"/api/sos/{sos[0]['id']}/acknowledge", headers=parent).json()["status"] == "acknowledged"
    assert client.post(f"/api/sos/{sos[0]['id']}/resolve", headers=parent).json()["status"] == "resolved"
    assert client.get("/api/sos", headers=parent).json() == []

    hist = client.get("/api/devices/SX-0001/history", headers=parent).json()
    assert len(hist) == 2

    # other user cannot see device until shared
    dad = _user(client, "dad@example.com")
    assert client.get("/api/devices/SX-0001", headers=dad).status_code == 404
    assert client.post("/api/devices/SX-0001/share", headers=parent, json={"email": "dad@example.com"}).status_code == 200
    assert client.get("/api/devices/SX-0001", headers=dad).status_code == 200

    # low battery alert flag
    client.post("/api/device/telemetry", headers=dev_h, json={"bat": 10})
    assert client.get("/api/devices/SX-0001", headers=parent).json()["battery"] == 10
