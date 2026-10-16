"""Assistant agent: local multi-step planner + LLM tool-calling loop (mocked OpenAI-compatible model)."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import agent, ai, llm
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Device, Location

SCHOOL, HOME = (12.9300, 77.6200), (12.9500, 77.6400)


def _setup(c):
    prov = c.post("/api/admin/devices", json={"device_id": "SX-AG"}, headers={"X-Admin-Key": "test-admin"}).json()
    h = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": "ag@x.com", "name": "A",
                                                                        "password": "secret123"}).json()["access_token"]}
    c.post("/api/devices/claim", headers=h, json={"device_id": "SX-AG", "claim_code": prov["claim_code"], "name": "Babai"})
    c.post("/api/admin/users/plan", headers={"X-Admin-Key": "test-admin"}, json={"email": "ag@x.com", "plan": "smart"})
    for n, p in (("School", SCHOOL), ("Home", HOME)):
        c.post("/api/devices/SX-AG/geofences", headers=h, json={"name": n, "lat": p[0], "lon": p[1], "radius_m": 100})
    c.put("/api/devices/SX-AG/setup", headers=h, json={"public_holidays": False})
    ist = ai.tz()
    today = datetime.now(ist).date()
    T = lambda d, hh, mm: datetime(d.year, d.month, d.day, hh, mm, tzinfo=ist).astimezone(timezone.utc)
    with SessionLocal() as db:
        dev = db.query(Device).filter_by(device_id="SX-AG").one()
        for k in range(1, 15):
            d = today - timedelta(days=k)
            late = 25 if k in (2, 3) else 0                      # late to school twice recently
            for i in range(0, 61, 10):
                db.add(Location(device_pk=dev.id, ts=T(d, 7, 0) + timedelta(minutes=i), lat=HOME[0], lon=HOME[1], speed=0))
            for i in range(0, 121, 10):
                db.add(Location(device_pk=dev.id, ts=T(d, 8, 30 + late) + timedelta(minutes=i), lat=SCHOOL[0], lon=SCHOOL[1], speed=0))
        dev.last_lat, dev.last_lon, dev.last_seen, dev.battery = HOME[0], HOME[1], datetime.now(timezone.utc), 70
        db.commit()
        ai.learn(db, dev)
        db.commit()
    return h


def test_agent_local_and_llm(monkeypatch):
    with TestClient(app) as c:
        h = _setup(c)
        ask = lambda q, hist=None: c.post("/api/devices/SX-AG/ask", headers=h,
                                           json={"question": q, "history": hist or []}).json()

        r = ask("Was Babai late to school this week compared to last week?")
        assert r["engine"] == "local" and "Last week" in r["answer"] and "This week" in r["answer"]
        assert "place_visits" in r["tools_used"]

        r = ask("how many times did he go to school in the last 7 days")
        assert "School" in r["answer"] and "of" in r["answer"]

        r = ask("any problem last week?")
        assert "No SOS" in r["answer"] or "SOS" in r["answer"]

        r = ask("where is babai now? and how far did he travel yesterday")      # two questions in one
        assert "Home" in r["answer"] and "km" in r["answer"]

        r = ask("Where is babai now ? when he reached at school ? and expected time to come back from school to home ?")
        parts = r["answer"].split("\n\n")
        assert len(parts) == 3 and "reached School at 08:30" in r["answer"] or "has not been at School" in r["answer"]
        assert "Home" in parts[-1]

        # typos are understood
        from app import agent as ag
        with SessionLocal() as db:
            dev = db.query(Device).filter_by(device_id="SX-AG").one()
            t = ag.Tools(db, dev)
            assert ag.normalize(t, "wher is babui now? did he reched scool safly") == "where is babai now? did he reached school safely"
        r = ask("wen did babui reched skool yesterdy?")
        assert "School" in r["answer"] and ("reached" in r["answer"] or "has been" in r["answer"])
        assert "Battery" in ask("batery?")["answer"]

        # ---- any OpenAI-compatible model (mocked): the model calls a tool, then answers
        calls = []

        def fake_chat(messages, tools=None, max_tokens=400):
            calls.append(messages[-1])
            if messages[-1]["role"] == "user":
                return {"content": "", "tool_calls": [{"id": "c1", "type": "function",
                        "function": {"name": "current_status", "arguments": "{}"}}]}
            assert messages[-1]["role"] == "tool" and '"place": "Home"' in messages[-1]["content"]
            return {"content": "Babai is at Home (updated just now). Battery 70%."}

        monkeypatch.setattr(settings, "llm_provider", "openai")
        monkeypatch.setattr(llm, "_openai_chat", fake_chat)
        r = ask("kahan hai babai?")
        assert r["engine"] == "openai" and r["answer"].startswith("Babai is at Home") and r["tools_used"] == ["current_status"]

        # model fails -> safe fallback to the local planner
        monkeypatch.setattr(llm, "_openai_chat", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
        r = ask("where is babai now?")
        assert r["engine"] == "local" and "Home" in r["answer"]


def test_parse_range():
    from datetime import date
    t = date(2026, 10, 4)                                         # Sunday
    assert agent.parse_range("this week", t)[:2] == (date(2026, 9, 28), t)
    assert agent.parse_range("last week", t)[:2] == (date(2026, 9, 21), date(2026, 9, 27))
    assert agent.parse_range("last 5 days", t)[:2] == (date(2026, 9, 30), t)
    assert agent.parse_range("on monday", t)[0] == date(2026, 9, 28)
    assert agent.parse_range("3 oct", t)[0] == date(2026, 10, 3)
