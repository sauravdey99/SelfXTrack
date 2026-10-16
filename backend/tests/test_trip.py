"""Live trip: start time/place, distance so far, destination + ETA before any routine is learned; no coordinates."""
import time

from fastapi.testclient import TestClient

from app.main import app

SCHOOL = (12.9720, 77.5972)
START, NOW_AT = (12.9560, 77.5810), (12.9668, 77.5918)


def test_live_trip_answers():
    with TestClient(app) as c:
        prov = c.post("/api/admin/devices", json={"device_id": "SX-TR"}, headers={"X-Admin-Key": "test-admin"}).json()
        h = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": "tr@x.com", "name": "T",
                                                                            "password": "secret123"}).json()["access_token"]}
        c.post("/api/devices/claim", headers=h, json={"device_id": "SX-TR", "claim_code": prov["claim_code"], "name": "Babai"})
        c.post("/api/admin/users/plan", headers={"X-Admin-Key": "test-admin"}, json={"email": "tr@x.com", "plan": "smart"})
        c.post("/api/devices/SX-TR/geofences", headers=h, json={"name": "School", "lat": SCHOOL[0], "lon": SCHOOL[1],
                                                               "radius_m": 300})
        dh = {"X-Device-Id": "SX-TR", "X-Device-Secret": prov["device_secret"]}
        now = int(time.time())
        for m in range(30, 13, -2):                                    # 16 min stay at the start
            c.post("/api/device/telemetry", headers=dh, json={"t": now - m * 60, "lat": START[0], "lon": START[1], "spd": 0})
        for i in range(13):                                            # 12 min on the way to school
            f = (i + 1) / 13
            c.post("/api/device/telemetry", headers=dh, json={
                "t": now - (12 - i) * 60, "lat": START[0] + (NOW_AT[0] - START[0]) * f,
                "lon": START[1] + (NOW_AT[1] - START[1]) * f, "spd": 12, "bat": 64})
        ask = lambda q, lg="en": c.post("/api/devices/SX-TR/ask", headers=h, json={"question": q, "lang": lg}).json()["answer"]

        a = ask("where is babai now?")
        assert "Left" in a and "km so far" in a and "heading to School" in a and "expected ~" in a
        assert "12.96" not in a and "77.5" not in a                    # never raw coordinates
        a = ask("when will babai reach school?")
        assert "on the way to School" in a and "Expected around" in a
        assert "पहुँचने का अनुमान" in ask("बबाई स्कूल कब पहुँचेगा?", "hi")
        assert "পৌঁছাবে" in ask("babai kothai ekhn?", "bn")
