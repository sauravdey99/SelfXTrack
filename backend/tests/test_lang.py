"""Regional-language questions: keyword mapping, translated built-in answers, language passed to the LLM."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import agent, ai, lang, llm
from app.db import SessionLocal
from app.main import app
from app.models import Device, Location

SCHOOL, HOME = (12.9300, 77.6200), (12.9500, 77.6400)


def test_keywords_map_regional_words():
    assert "where" in lang.keywords("बबाई अभी कहाँ है?") and "now" in lang.keywords("बबाई अभी कहाँ है?")
    k = lang.keywords("বাবাই কখন স্কুলে পৌঁছেছে?")
    assert "when" in k and "school" in k and "reached" in k
    assert "where" in lang.keywords("பாபாய் இப்போது எங்கே?")
    assert "missing" in lang.keywords("बबाई खो गया")                    # emergency words work in any language
    assert lang.keywords("where is babai") == "where is babai"


def test_localize_status_and_arrival():
    s = "📍 Babai is at Home (updated 08:10, just now). ✅ That's where Babai usually is at this time.\n🔋 Battery 70% · ✅ No SOS."
    hi = lang.localize(s, "hi")
    assert "घर पर है" in hi and "अभी-अभी" in hi and "बैटरी 70%" in hi and "कोई SOS नहीं" in hi
    bn = lang.localize("✅ Babai reached School at 08:30 today and is still there.", "bn")
    assert bn == "✅ Babai আজ 08:30-এ স্কুল-এ পৌঁছেছে এবং এখনও সেখানেই আছে।"
    assert lang.localize(s, "xx") == s                                  # unknown language -> English


def test_localize_every_language():
    """Built-in answers exist in all 12 Indian languages: no English sentence left, names and numbers kept."""
    s = ("📍 Babai is near Sampangi Rama Nagara, moving at 12 km/h (updated 01:16, 2 min ago).\n"
         "🚶 Left JC Road at 01:04 · 1.7 km so far · heading to School, expected ~01:26 (8 min).\n🔋 Battery 64% · ✅ No SOS.")
    for code in lang.SUPPORTED:
        if code == "en":
            continue
        out = lang.localize(s, code)
        assert "Babai" in out and "01:26" in out and "64%" in out, code
        for english in ("is near", "moving at", "so far", "heading to", "Battery", "No SOS"):
            assert english not in out, (code, english)
        assert "112" in lang.localize("🚨 If you think Babai is in danger, call 112 now. In the app: x so nearby people can help.", code)


def _setup(c):
    prov = c.post("/api/admin/devices", json={"device_id": "SX-LG"}, headers={"X-Admin-Key": "test-admin"}).json()
    h = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": "lg@x.com", "name": "L",
                                                                        "password": "secret123"}).json()["access_token"]}
    c.post("/api/devices/claim", headers=h, json={"device_id": "SX-LG", "claim_code": prov["claim_code"], "name": "Babai"})
    c.post("/api/admin/users/plan", headers={"X-Admin-Key": "test-admin"}, json={"email": "lg@x.com", "plan": "smart"})
    for n, p in (("School", SCHOOL), ("Home", HOME)):
        c.post("/api/devices/SX-LG/geofences", headers=h, json={"name": n, "lat": p[0], "lon": p[1], "radius_m": 100})
    c.put("/api/devices/SX-LG/setup", headers=h, json={"public_holidays": False})
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        dev = db.query(Device).filter_by(device_id="SX-LG").one()
        db.add(Location(device_pk=dev.id, ts=now - timedelta(minutes=1), lat=HOME[0], lon=HOME[1], speed=0))
        dev.last_lat, dev.last_lon, dev.last_seen, dev.battery = HOME[0], HOME[1], now, 70
        db.commit()
    return h


def test_ask_in_regional_languages(monkeypatch):
    with TestClient(app) as c:
        h = _setup(c)
        ask = lambda q, lg: c.post("/api/devices/SX-LG/ask", headers=h, json={"question": q, "lang": lg}).json()

        r = ask("बबाई अभी कहाँ है?", "hi")
        assert r["engine"] == "local" and "घर पर है" in r["answer"]
        r = ask("বাবাই এখন কোথায়?", "bn")
        assert "বাড়ি-এ আছে" in r["answer"]
        r = ask("बबाई खो गया है", "hi")                                    # emergency guardrail, translated
        assert r["engine"] == "guardrail" and "112" in r["answer"] and "खतरे" in r["answer"]
        r = ask("பாபாய் இப்போது எங்கே?", "ta")                             # understood, built-in answer in Tamil
        assert r["engine"] == "local" and "📍" in r["answer"] and " is at " not in r["answer"]
        assert ask("where is babai now", "en")["answer"].startswith("📍 Babai is at Home")

        # with an LLM: the language goes into the system prompt, and unknown regional words are not blocked
        seen = {}

        def fake_chat(messages, tools=None, max_tokens=400):
            seen["system"] = messages[0]["content"]
            return {"content": "பாபாய் இப்போது வீட்டில் இருக்கிறார்."}
        monkeypatch.setattr(llm, "provider", lambda: "openai")
        monkeypatch.setattr(llm, "_openai_chat", fake_chat)
        r = ask("பாபாய் சாப்பிட்டாரா?", "ta")                              # no mapped keyword in this question
        assert r["engine"] == "openai" and "Tamil in Tamil script" in seen["system"]
        assert r["answer"].startswith("பாபாய்")
