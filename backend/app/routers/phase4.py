"""Phase 4: AI insights / summary / assistant / incident report + plans & Razorpay billing."""
import hashlib
import hmac
import json
from datetime import date, datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import push_msgs
from .. import ai, llm
from ..config import settings
from ..db import get_db
from ..models import AiAlert, Device, Payment, SosEvent, User
from ..plans import PLANS, allows, effective_plan
from ..security import current_user
from ..services import as_utc
from ..services_help import device_plan
from .devices import _get_member_device

router = APIRouter(prefix="/api", tags=["phase4"])


def _need(db: Session, dev: Device, feature: str):
    plan = device_plan(db, dev)
    if not allows(plan, feature):
        need = "Guardian" if feature in ("risk", "report") else "Smart"
        raise HTTPException(402, f"This feature needs the {need} plan.")
    return plan


# ---------------- AI ----------------
@router.get("/devices/{device_id}/insights")
def insights(device_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    plan = device_plan(db, dev)
    if not allows(plan, "ai"):
        return {"locked": True, "plan": plan}
    model = ai.get_model(db, dev)
    alerts = db.scalars(select(AiAlert).where(AiAlert.device_pk == dev.id).order_by(AiAlert.ts.desc()).limit(10)).all()
    out = {"locked": False, "plan": plan, "learning_days": model.days, "ready": model.days >= settings.ai_min_days,
           "min_days": settings.ai_min_days, "places": json.loads(model.places), "eta": ai.eta(db, dev),
           "trips": [{k: t[k] for k in ("from", "to", "median_min", "usual_depart", "usual_arrive", "count")}
                     for t in json.loads(model.trips or "{}").get("trips", [])],
           "alerts": [{"time": ai.local(a.ts).strftime("%d %b %H:%M"), "kind": a.kind,
                       "text": push_msgs.alert_text(a.kind, a.text, a.msg_args, user.lang)} for a in alerts],
           "assistant_ai": llm.enabled(), "battery": ai.battery_forecast(db, dev), "holiday_today": ai.is_holiday(db, dev, datetime.now(ai.tz()).date()),
           "holiday_question": ai._holiday_state(db, dev, datetime.combine(datetime.now(ai.tz()).date(),
                                                 datetime.min.time(), ai.tz()).astimezone(timezone.utc)) == "asked"}
    db.commit()
    return out


@router.post("/devices/{device_id}/learn")
def relearn(device_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    _need(db, dev, "ai")
    m = ai.learn(db, dev)
    db.commit()
    return {"days": m.days, "places": json.loads(m.places)}


@router.get("/devices/{device_id}/summary")
def day_summary(device_id: str, day: date | None = None, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    _need(db, dev, "ai")
    out = ai.summary(db, dev, day or datetime.now(ai.tz()).date())
    db.commit()
    return out


def _check_history_day(db: Session, dev: Device, d: date) -> str:
    """Today + yesterday: every plan. Custom dates: Smart (₹299) and above, within the plan's history."""
    from ..plans import PLANS
    plan = device_plan(db, dev)
    age = (datetime.now(ai.tz()).date() - d).days
    if age < 0:
        raise HTTPException(400, "Date is in the future")
    if age > 1 and not allows(plan, "ai"):
        raise HTTPException(402, "Custom dates need the Smart plan (₹299) or above.")
    if age >= PLANS[plan]["history_days"]:
        raise HTTPException(402, f"Your plan keeps {PLANS[plan]['history_days']} days of history.")
    return plan


@router.get("/devices/{device_id}/days")
def days(device_id: str, start: date | None = None, end: date | None = None, user: User = Depends(current_user),
         db: Session = Depends(get_db)):
    """History rows. No dates = today + yesterday. start/end = custom range (Smart+), max 31 days."""
    dev = _get_member_device(db, user, device_id)
    today = datetime.now(ai.tz()).date()
    end = end or (today if start is None else start)
    start = start or today - timedelta(days=1)
    if start > end:
        start, end = end, start
    if (end - start).days > 29:
        raise HTTPException(400, "Up to 30 days")
    dates = [start + timedelta(days=k) for k in range((end - start).days + 1)]
    for d in (dates[0], dates[-1]):
        _check_history_day(db, dev, d)
    out = ai.day_list(db, dev, dates)
    db.commit()
    return out


@router.get("/devices/{device_id}/day")
def day(device_id: str, day: date, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    _check_history_day(db, dev, day)
    out = ai.day_detail(db, dev, day)
    db.commit()
    return out


@router.get("/devices/{device_id}/weekly")
def weekly(device_id: str, week_start: date | None = None, user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    _need(db, dev, "ai")
    out = ai.weekly_report(db, dev, week_start)
    db.commit()
    return out


@router.get("/devices/{device_id}/routine")
def routine(device_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    _need(db, dev, "ai")
    out = ai.routine(db, dev)
    db.commit()
    return out


# ---------------- holidays ----------------
class HolidayIn(BaseModel):
    start: date
    end: date | None = None
    note: str | None = None
    all_children: bool = True


def _family_devices(db: Session, user: User, dev: Device) -> list[Device]:
    from ..models import DeviceMember
    owned = db.scalars(select(Device).join(DeviceMember, DeviceMember.device_pk == Device.id)
                       .where(DeviceMember.user_id == user.id, DeviceMember.role == "owner")).all()
    return list(owned) or [dev]


@router.get("/devices/{device_id}/holidays")
def list_holidays(device_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..models import Holiday
    dev = _get_member_device(db, user, device_id)
    from ..holidays_in import HOLIDAYS
    today = datetime.now(ai.tz()).date().isoformat()
    own = [{"day": h.day, "note": h.note, "public": False} for h in db.scalars(select(Holiday).where(
        Holiday.device_pk == dev.id, Holiday.day >= today).order_by(Holiday.day)).all()]
    pub = [{"day": d, "note": n, "public": True} for d, n in HOLIDAYS.items()
           if d >= today and dev.public_holidays is not False and all(o["day"] != d for o in own)][:6]
    return sorted(own + pub, key=lambda x: x["day"])


@router.post("/devices/{device_id}/holidays")
def add_holidays(device_id: str, body: HolidayIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Holiday / vacation: routine alerts pause on these days (SOS, safe zones, unusual route keep working)."""
    dev = _get_member_device(db, user, device_id)
    end = body.end or body.start
    if end < body.start or (end - body.start).days > 90:
        raise HTTPException(400, "Pick up to 90 days")
    days_ = [body.start + timedelta(days=k) for k in range((end - body.start).days + 1)]
    for d in (_family_devices(db, user, dev) if body.all_children else [dev]):
        ai.set_holidays(db, d, user, days_, body.note)
    db.commit()
    return list_holidays(device_id, user, db)


@router.delete("/devices/{device_id}/holidays/{day}")
def delete_holiday(device_id: str, day: date, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..models import Holiday
    dev = _get_member_device(db, user, device_id)
    for d in _family_devices(db, user, dev):
        for h in db.scalars(select(Holiday).where(Holiday.device_pk == d.id, Holiday.day == day.isoformat())).all():
            db.delete(h)
    db.commit()
    return list_holidays(device_id, user, db)


class HolidayAnswerIn(BaseModel):
    holiday: bool


@router.post("/devices/{device_id}/holiday-answer")
def holiday_answer(device_id: str, body: HolidayAnswerIn, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    ai.answer_holiday(db, dev, user, body.holiday)
    db.commit()
    return {"ok": True}


class RouteOkIn(BaseModel):
    learn: bool = False                 # "This is a regular route" – learn the cells of this trip now
    hours: int | None = None            # older apps: 1–8 h timed pause
    minutes: int | None = None          # 15–480 min timed pause; both None = this trip only (ends at the next known place, max 3 h)


@router.post("/devices/{device_id}/route-ok")
def route_ok(device_id: str, body: RouteOkIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """"It's OK – I know" on a route alert, or "Pause route alerts" on the map. Never pauses SOS, fall, offline,
    battery or Places schedule alerts. Ends by itself."""
    from .. import push_msgs
    from ..services import device_users
    dev = _get_member_device(db, user, device_id)
    now = datetime.now(timezone.utc)
    minutes = body.minutes if body.minutes is not None else (body.hours * 60 if body.hours is not None else None)
    trip = minutes is None
    minutes = 180 if trip else max(15, min(int(minutes), 480))
    dev.route_ok_until, dev.route_ok_by, dev.route_ok_trip = now + timedelta(minutes=minutes), user.id, trip
    learned = 0
    if body.learn:
        learned = ai.learn_now(db, dev, now - timedelta(hours=3))
    key = "route_ok" if trip else "route_pause"
    p = {"label": dev.name or dev.device_id, "by": user.name, "until": ai.hhmm(dev.route_ok_until)}
    title, text = push_msgs.render(key, "en", **p)
    db.add(AiAlert(device_pk=dev.id, kind=key, text=text, msg_args=push_msgs.args_json(_key=key, **p)))
    db.commit()
    others = [u for u in device_users(db, dev) if u.id != user.id]
    push_msgs.push(others, key, {"type": "route_ok", "device_id": dev.device_id, "name": p["label"], "text": text}, **p)
    return {"until": p["until"], "trip": trip, "learned_points": learned}


@router.delete("/devices/{device_id}/route-ok")
def route_resume(device_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    dev.route_ok_until = None
    db.commit()
    return {"ok": True}


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=300)
    history: list[dict] = []      # [{"role": "user"|"assistant", "text": "..."}] – last turns for follow-ups
    lang: str = "en"              # answer language: en / hi / bn


@router.post("/devices/{device_id}/ask")
def ask(device_id: str, body: AskIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    _need(db, dev, "ai")
    from .. import agent
    out = agent.answer(db, dev, body.question, body.history, user_id=user.id, lang=body.lang)
    db.commit()
    return out


@router.get("/ai/status")
def ai_status(user: User = Depends(current_user)):
    """Which engine answers 'Ask' questions, and is the AI model reachable right now?"""
    from ..llm import _openai_chat, provider
    prov = provider()
    out = {"engine": prov or "local", "model": None, "reachable": None, "error": None}
    if prov == "openai":
        out["model"] = settings.llm_model
        try:
            _openai_chat([{"role": "user", "content": "Reply with OK"}], max_tokens=5)
            out["reachable"] = True
        except Exception as e:
            out["reachable"], out["error"] = False, str(e)[:200]
    elif prov == "anthropic":
        out["model"], out["reachable"] = settings.anthropic_model, llm.complete("Reply with OK", {}, 5) is not None
    return out


@router.get("/sos/{sos_id}/report")
def report(sos_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ev = db.get(SosEvent, sos_id)
    if ev is None:
        raise HTTPException(404, "SOS not found")
    dev = _get_member_device(db, user, db.get(Device, ev.device_pk).device_id)
    _need(db, dev, "report")
    return ai.incident_report(db, ev)


# ---------------- Plans & billing ----------------
@router.get("/plans")
def plans():
    return [{"id": k, **v} for k, v in PLANS.items()]


def _billing_me(u: User) -> dict:
    return {"plan": effective_plan(u), "paid_plan": u.plan, "status": u.plan_status,
            "expires_at": as_utc(u.plan_expires_at).isoformat() if u.plan_expires_at else None,
            "grace_days": settings.grace_days, "mode": "razorpay" if settings.razorpay_key_id else "dev"}


@router.get("/billing/me")
def billing_me(user: User = Depends(current_user)):
    return _billing_me(user)


class SubscribeIn(BaseModel):
    plan: str
    period: str = "monthly"   # monthly / yearly


def _activate(db: Session, u: User, plan: str, period: str, until: datetime | None = None):
    base = as_utc(u.plan_expires_at) if u.plan_expires_at and u.plan == plan and \
        as_utc(u.plan_expires_at) > datetime.now(timezone.utc) else datetime.now(timezone.utc)
    u.plan, u.plan_status = plan, "active"
    u.plan_expires_at = until or base + timedelta(days=365 if period == "yearly" else 30)


@router.post("/billing/subscribe")
def subscribe(body: SubscribeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.plan not in PLANS or body.period not in ("monthly", "yearly"):
        raise HTTPException(400, "Unknown plan")
    amount = PLANS[body.plan][body.period]
    pay = Payment(user_id=user.id, plan=body.plan, period=body.period, amount_inr=amount)
    db.add(pay)
    db.flush()
    if not settings.razorpay_key_id:            # dev mode: confirm in the app
        db.commit()
        return {"mode": "dev", "payment_id": pay.id, "amount_inr": amount}
    plan_id = settings.razorpay_plan_ids.get(f"{body.plan}_{body.period}")
    if not plan_id:
        raise HTTPException(500, f"Razorpay plan id missing for {body.plan}_{body.period}")
    r = httpx.post("https://api.razorpay.com/v1/subscriptions",
                   auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
                   json={"plan_id": plan_id, "total_count": 10 if body.period == "yearly" else 120,
                         "customer_notify": 1, "notes": {"user_id": str(user.id), "plan": body.plan,
                                                          "period": body.period, "payment_id": str(pay.id)}},
                   timeout=20)
    if r.status_code >= 300:
        raise HTTPException(502, "Payment service error. Try again.")
    sub = r.json()
    pay.razorpay_sub_id = user.razorpay_sub_id = sub["id"]
    db.commit()
    return {"mode": "razorpay", "payment_id": pay.id, "amount_inr": amount, "checkout_url": sub.get("short_url")}


@router.post("/billing/dev-confirm/{payment_id}")
def dev_confirm(payment_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if settings.razorpay_key_id:
        raise HTTPException(403, "Not available with real payments")
    pay = db.get(Payment, payment_id)
    if pay is None or pay.user_id != user.id or pay.status != "created":
        raise HTTPException(404, "Payment not found")
    pay.status = "paid"
    _activate(db, user, pay.plan, pay.period)
    db.commit()
    return _billing_me(user)


@router.post("/billing/cancel")
def cancel(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Stops renewal. The plan stays until the end of the paid period."""
    if settings.razorpay_key_id and user.razorpay_sub_id:
        httpx.post(f"https://api.razorpay.com/v1/subscriptions/{user.razorpay_sub_id}/cancel",
                   auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
                   json={"cancel_at_cycle_end": 1}, timeout=20)
    user.plan_status = "cancelled"
    db.commit()
    return _billing_me(user)


@router.post("/billing/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    """Razorpay → server. Verifies X-Razorpay-Signature (HMAC-SHA256 of the raw body)."""
    raw = await request.body()
    sig = request.headers.get("X-Razorpay-Signature", "")
    secret = (settings.razorpay_webhook_secret or "").encode()
    if not secret or not hmac.compare_digest(hmac.new(secret, raw, hashlib.sha256).hexdigest(), sig):
        raise HTTPException(400, "Bad signature")
    evt = json.loads(raw)
    sub = evt.get("payload", {}).get("subscription", {}).get("entity", {})
    notes = sub.get("notes") or {}
    user = db.get(User, int(notes["user_id"])) if notes.get("user_id") else \
        db.scalar(select(User).where(User.razorpay_sub_id == sub.get("id")))
    if user is None:
        return {"ok": True}
    kind = evt.get("event", "")
    if kind in ("subscription.activated", "subscription.charged"):
        end = sub.get("current_end")
        _activate(db, user, notes.get("plan", user.plan), notes.get("period", "monthly"),
                  datetime.fromtimestamp(end, tz=timezone.utc) if end else None)
        pay_id = notes.get("payment_id")
        if pay_id and (pay := db.get(Payment, int(pay_id))):
            pay.status = "paid"
            pay.razorpay_payment_id = evt.get("payload", {}).get("payment", {}).get("entity", {}).get("id")
    elif kind in ("subscription.halted", "subscription.pending"):
        user.plan_status = "past_due"          # grace period applies; SOS keeps working
    elif kind in ("subscription.cancelled", "subscription.completed"):
        user.plan_status = "cancelled"
    db.commit()
    return {"ok": True}


@router.get("/family/brief")
def family_brief(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """One at-a-glance status per tracker for the family screen ("At School since 08:04 · on time · next Home ~16:25").
    Facts from GPS + schedule + learned routine – no AI model, so it is free for every plan and always consistent
    with what the assistant says."""
    import logging
    from ..models import DeviceMember
    devs = db.scalars(select(Device).join(DeviceMember).where(DeviceMember.user_id == user.id)).all()
    out = []
    for d in devs:
        try:
            out.append({"device_id": d.device_id, **ai.brief(db, d, user.lang or "en")})
        except Exception:                                    # one broken tracker must not hide the others
            logging.getLogger("selfx.brief").exception("brief failed for %s", d.device_id)
            out.append({"device_id": d.device_id, "state": "unknown"})
    return out
