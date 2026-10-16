"""Places (home, school, tuition, swimming, grandma's …), their time slots and the people responsible there.

- schedule: [{"days": [0..6 Mon..Sun], "start": "HH:MM", "end": "HH:MM"}] – times in IST
- current_context(): where the child should be right now and who is responsible there
- check_schedules(): "not at Swimming by 07:15" / "left Swimming early" alerts (every minute + on geofence exit)
- escalate_place(): Emergency – alert the people at the current place (coach, tutor …)
- migrate(): one-time, idempotent move of older data (safe-zone names -> kinds, school contacts, buses)
"""
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AiAlert, Bus, Device, DeviceBus, Geofence, SosEvent, TeacherContact, Transport, User

log = logging.getLogger("selfx.places")

KINDS = ("home", "school", "class", "activity", "family", "other")
TRANSPORT_KINDS = ("bus", "van", "auto", "cab", "other")
ROLES = ("teacher", "staff", "coach", "tutor", "caretaker", "driver", "other")
MAX_PLACES = 50
LATE_AFTER_MIN = 15          # "not there yet" after start + 15 min
EARLY_BEFORE_MIN = 10        # "left early" if it leaves more than 10 min before the end
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


# ---------------------------------------------------------------- schedule helpers
def parse_schedule(raw) -> list[dict]:
    """Validate + normalise slots. Raises ValueError with a readable message."""
    if raw in (None, "", []):
        return []
    slots = json.loads(raw) if isinstance(raw, str) else raw
    out = []
    for s in slots:
        days = sorted({int(d) for d in s.get("days", [])})
        start, end = str(s.get("start", "")), str(s.get("end", ""))
        if not days or any(d < 0 or d > 6 for d in days):
            raise ValueError("Choose at least one day")
        if not _TIME.match(start) or not _TIME.match(end):
            raise ValueError("Time must be HH:MM")
        if end <= start:
            raise ValueError("End time must be after start time")
        out.append({"days": days, "start": start, "end": end})
    if len(out) > 14:
        raise ValueError("Maximum 14 time slots per place")
    return out


def slots_on(place: Geofence, day: date) -> list[dict]:
    try:
        return [s for s in parse_schedule(place.schedule) if day.weekday() in s["days"]]
    except (ValueError, TypeError):
        return []


def _at(day: date, hm: str, tz) -> datetime:
    h, m = map(int, hm.split(":"))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=tz).astimezone(timezone.utc)


def kind_from_name(name: str) -> str:
    n = (name or "").lower()
    for kind, words in (("home", ("home", "house", "ghar", "flat")), ("school", ("school", "vidyalaya", "college")),
                        ("class", ("tuition", "tution", "coaching", "class")),
                        ("activity", ("swim", "dance", "music", "karate", "sport", "cricket", "football", "gym", "art")),
                        ("family", ("nani", "dadi", "nana", "dada", "grand", "aunt", "uncle", "mama", "chacha"))):
        if any(w in n for w in words):
            return kind
    return "other"


def is_at(dev: Device, g: Geofence) -> bool:
    """From the last location (not the stored enter/exit flag, which is empty until the first change)."""
    from .services import distance_m
    if dev.last_lat is None:
        return False
    return distance_m(dev.last_lat, dev.last_lon, g.lat, g.lon) <= g.radius_m + min(dev.last_accuracy or 0, 50)


def people(db: Session, place: Geofence) -> list[TeacherContact]:
    return list(db.scalars(select(TeacherContact).where(TeacherContact.place_id == place.id)).all())


# ---------------------------------------------------------------- where should the child be now?
def current_context(db: Session, dev: Device, now: datetime | None = None) -> dict:
    """{"place": {...} | None, "until": "HH:MM", "inside": bool, "people": [...]} for the slot active right now."""
    from .ai import tz
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(tz()).date()
    for g in db.scalars(select(Geofence).where(Geofence.device_pk == dev.id)).all():
        for s in slots_on(g, today):
            if _at(today, s["start"], tz()) <= now < _at(today, s["end"], tz()):
                return {"place": {"id": g.id, "name": g.name, "kind": g.kind}, "from": s["start"], "until": s["end"],
                        "inside": is_at(dev, g),
                        "people": [{"name": c.name, "role": c.role, "phone": c.phone} for c in people(db, g)]}
    return {"place": None}


def schedule_today(db: Session, dev: Device, day: date | None = None) -> list[dict]:
    from .ai import tz
    day = day or datetime.now(tz()).date()
    out = []
    for g in db.scalars(select(Geofence).where(Geofence.device_pk == dev.id)).all():
        for s in slots_on(g, day):
            out.append({"place": g.name, "kind": g.kind, "start": s["start"], "end": s["end"]})
    return sorted(out, key=lambda x: x["start"])


# ---------------------------------------------------------------- late / left-early alerts
def _already(db: Session, dev: Device, kind: str, key: str) -> bool:
    """The key holds place + date + slot start, so it is unique per slot; look only at recent alerts."""
    since = datetime.now(timezone.utc) - timedelta(days=2)
    return any(f'"slot": "{key}"' in (a.msg_args or "") for a in db.scalars(select(AiAlert).where(
        AiAlert.device_pk == dev.id, AiAlert.kind == kind, AiAlert.ts >= since)).all())


def _alert(db: Session, dev: Device, kind: str, key: str, **p):
    from . import push_msgs
    from .realtime import manager
    from .services import device_users
    users = device_users(db, dev)
    p.setdefault("label", dev.name or dev.device_id)
    title, text = push_msgs.render(kind, "en", **p)
    db.add(AiAlert(device_pk=dev.id, kind=kind, text=text, msg_args=push_msgs.args_json(_key=kind, slot=key, **p),
                   lat=dev.last_lat, lon=dev.last_lon))
    db.flush()                                 # sessions do not autoflush – the once-per-slot check must see it
    push_msgs.push(users, kind, {"type": "ai_alert", "kind": kind, "device_id": dev.device_id, "text": text,
                                 "name": p["label"]}, **p)
    by_lang: dict[str, list[int]] = {}
    for u in users:
        by_lang.setdefault(getattr(u, "lang", None) or "en", []).append(u.id)
    for lang, ids in by_lang.items():
        manager.publish(ids, {"type": "ai_alert", "kind": kind, "device_id": dev.device_id,
                              "text": push_msgs.render(kind, lang, **p)[1]})


def _skip_day(db: Session, dev: Device, g: Geofence, day: date) -> bool:
    from .ai import is_holiday
    return g.kind in ("school", "class") and is_holiday(db, dev, day)


def check_schedules(db: Session, dev: Device, now: datetime | None = None) -> int:
    """'Not there yet' alerts. Called every minute from the monitor loop."""
    from .ai import hhmm, tz
    from .config import settings
    now = now or datetime.now(timezone.utc)
    from .services import as_utc
    if dev.last_seen is None or dev.last_lat is None or \
            now - as_utc(dev.last_seen) > timedelta(minutes=settings.offline_after_minutes):
        return 0                                   # offline -> the offline alert already covers it
    today = now.astimezone(tz()).date()
    n = 0
    for g in db.scalars(select(Geofence).where(Geofence.device_pk == dev.id, Geofence.alert_late.is_(True))).all():
        if _skip_day(db, dev, g, today):
            continue
        for s in slots_on(g, today):
            start, end = _at(today, s["start"], tz()), _at(today, s["end"], tz())
            key = f"{g.id}@{today.isoformat()}@{s['start']}"
            if start + timedelta(minutes=LATE_AFTER_MIN) <= now < end and not is_at(dev, g) \
                    and not _already(db, dev, "sched_late", key):
                _alert(db, dev, "sched_late", key, place=g.name, start=s["start"], time=hhmm(now))
                n += 1
    return n


def on_exit(db: Session, dev: Device, g: Geofence, now: datetime | None = None) -> None:
    """Geofence exit during a slot, clearly before it ends -> 'left early'."""
    from .ai import hhmm, tz
    if not g.alert_late:
        return
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(tz()).date()
    if _skip_day(db, dev, g, today):
        return
    for s in slots_on(g, today):
        start, end = _at(today, s["start"], tz()), _at(today, s["end"], tz())
        key = f"{g.id}@{today.isoformat()}@{s['start']}"
        if start <= now < end - timedelta(minutes=EARLY_BEFORE_MIN) and \
                not _already(db, dev, "sched_early", key):
            _alert(db, dev, "sched_early", key, place=g.name, time=hhmm(now), end=s["end"])


# ---------------------------------------------------------------- who may see which SOS
def mark_alerted(sos: SosEvent, key: str) -> None:
    keys = json.loads(sos.alerted_to or "[]")
    if key not in keys:
        keys.append(key)
    sos.alerted_to = json.dumps(keys)
    sos.school_alerted = True


def alerted_keys(sos: SosEvent) -> set[str]:
    if sos.alerted_to:
        return set(json.loads(sos.alerted_to))
    return {"school"} if sos.school_alerted else set()     # SOS from before per-place alerts


def can_see(db: Session, sos: SosEvent, contact: TeacherContact) -> bool:
    """A teacher sees an SOS sent to the school; a coach / tutor only one sent to their place."""
    keys = alerted_keys(sos)
    if contact.place_id is None:
        return "school" in keys
    if f"place:{contact.place_id}" in keys:
        return True
    g = db.get(Geofence, contact.place_id)
    return g is not None and g.kind == "school" and "school" in keys


# ---------------------------------------------------------------- emergency: people at the current place
def escalate_place(db: Session, dev: Device, sos: SosEvent, by_user: User | None, place: Geofence) -> dict:
    """Alert the people responsible at `place` (coach, tutor, caretaker): SMS with a 3-hour live link, plus the
    in-app alert + caretaker dashboard for those who use SelfXTrack with the same verified number."""
    from . import notify
    from .realtime import manager
    from .services import device_users, sos_info
    from .services_help import _sos_link
    from .sms import send_sms
    contacts = people(db, place)
    if not contacts:
        return {"already": False, "people": 0, "place": place.name}
    first = f"place:{place.id}" not in alerted_keys(sos)
    mark_alerted(sos, f"place:{place.id}")     # these people see the child on their dashboard only from now on
    if sos.school_notified_at is None:
        sos.school_notified_at = datetime.now(timezone.utc)
    if by_user and not sos.escalated_by:
        sos.escalated_by = by_user.id
    label = dev.name or dev.device_id
    who = f" (requested by {by_user.name})" if by_user else " (no family response)"
    url = _sos_link(db, dev, sos, by_user.id if by_user else dev.members[0].user_id)
    for c in contacts:
        send_sms(c.phone, f"EMERGENCY at {place.name}: {label} needs help{who}. Live location: {url} . Call 112 if needed.")
    family = {u.id for u in device_users(db, dev)}
    app_users = [u for u in db.scalars(select(User).where(User.phone.in_([c.phone for c in contacts]),
                                                           User.phone_verified.is_(True))).all() if u.id not in family]
    info = {"type": "sos", "role": "school", "by": by_user.name if by_user else "", "place": place.name, **sos_info(dev, sos)}
    if app_users:
        notify.push(app_users, "🚨 Emergency", f"{label} needs help at {place.name}{who}.", info)
        manager.publish([u.id for u in app_users], info)
    db.commit()
    manager.publish([u.id for u in device_users(db, dev) if not by_user or u.id != by_user.id],
                    {"type": "school_escalated", "sos_id": sos.id, "device_id": dev.device_id, "place": place.name,
                     "contacts": len(contacts)})
    return {"already": not first, "people": len(contacts), "place": place.name}


# ---------------------------------------------------------------- one-time move of older data
def migrate(db: Session) -> None:
    """Idempotent: safe to run at every start."""
    changed = 0
    for g in db.scalars(select(Geofence).where(Geofence.kind.is_(None) | (Geofence.kind == "other"))).all():
        k = kind_from_name(g.name)
        if k != "other":
            g.kind, changed = k, changed + 1
    # older school contacts -> the child's (single) school place, if there is one
    for c in db.scalars(select(TeacherContact).where(TeacherContact.place_id.is_(None))).all():
        schools = db.scalars(select(Geofence).where(Geofence.device_pk == c.device_pk, Geofence.kind == "school")).all()
        if len(schools) == 1:
            c.place_id, changed = schools[0].id, changed + 1
    # buses -> transports
    for link in db.scalars(select(DeviceBus)).all():
        if db.scalar(select(Transport).where(Transport.device_pk == link.device_pk, Transport.bus_id == link.bus_id)):
            continue
        bus = db.get(Bus, link.bus_id)
        if bus:
            db.add(Transport(device_pk=link.device_pk, name=bus.name, kind="bus", bus_id=bus.id, created_by=bus.created_by))
            changed += 1
    if changed:
        db.commit()
        log.info("places migration: %s rows updated", changed)
