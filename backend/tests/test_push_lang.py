"""Server-written alerts go to each family member in their own app language."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import notify, push_msgs
from app.db import SessionLocal
from app.main import app
from app.models import Device
from app.push_msgs_tr import TR
from app.services_p5 import check_inactivity

A = {"X-Admin-Key": "test-admin"}


def _token(c, email):
    return {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": email, "name": email[:3],
                                                                           "password": "secret123"}).json()["access_token"]}


def test_catalog_complete():
    for lang, msgs in TR.items():
        assert set(msgs) == set(push_msgs.EN), lang
    p = dict(label="Babai", dst="School", median=20, src="Home", left="08:00", time="08:45", took=45, km="1.2")
    hi = push_msgs.render("late", "hi", **p)
    assert hi != push_msgs.render("late", "en", **p) and "Babai" in hi[1] and "1.2" in hi[1]
    assert push_msgs.render("late", "xx", **p) == push_msgs.render("late", "en", **p)      # unknown -> English


def test_alert_in_each_users_language(monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "push", lambda users, title, body, data, **k:
                        sent.extend((u.email, title, body, data.get("text")) for u in users))
    with TestClient(app) as c:
        dad, mom = _token(c, "dad-pl@x.com"), _token(c, "mom-pl@x.com")
        c.post("/api/admin/users/plan", headers=A, json={"email": "dad-pl@x.com", "plan": "guardian"})
        assert c.put("/api/auth/lang", headers=mom, json={"lang": "hi"}).json()["lang"] == "hi"
        assert c.put("/api/auth/lang", headers=dad, json={"lang": "zz"}).json()["lang"] == "en"   # unknown -> en
        prov = c.post("/api/admin/devices", json={"device_id": "SX-PL", "kind": "elderly"}, headers=A).json()
        c.post("/api/devices/claim", headers=dad, json={"device_id": "SX-PL", "claim_code": prov["claim_code"],
                                                        "name": "Dadi", "kind": "elderly"})
        assert c.post("/api/devices/SX-PL/share", headers=dad, json={"email": "mom-pl@x.com"}).status_code == 200
        c.put("/api/devices/SX-PL/care", headers=dad, json={"inactivity_hours": 2, "active_from": "00:00",
                                                            "active_to": "23:59"})
        with SessionLocal() as db:
            d = db.query(Device).filter_by(device_id="SX-PL").one()
            d.last_active_at = datetime.now(timezone.utc) - timedelta(hours=3)
            d.last_seen = datetime.now(timezone.utc)
            db.commit()
            sent.clear()
            check_inactivity(db)

        by = {e: (t, b, x) for e, t, b, x in sent}
        assert by["dad-pl@x.com"][0] == "🧓 Check on Dadi"
        hi_title, hi_body = push_msgs.render("inactivity", "hi", label="Dadi", hrs=2, since="x")
        assert by["mom-pl@x.com"][0] == hi_title and by["mom-pl@x.com"][0] != by["dad-pl@x.com"][0]
        assert by["mom-pl@x.com"][2] == by["mom-pl@x.com"][1]          # the phone shows data["text"] = localized body

        # alert list in the app: same saved alert, each reader sees their language
        ins_mom = c.get("/api/devices/SX-PL/insights", headers=mom).json()
        ins_dad = c.get("/api/devices/SX-PL/insights", headers=dad).json()
        a_mom = next(a for a in ins_mom["alerts"] if a["kind"] == "inactivity")
        a_dad = next(a for a in ins_dad["alerts"] if a["kind"] == "inactivity")
        assert a_dad["text"].startswith("No movement from Dadi") and a_mom["text"] != a_dad["text"]
