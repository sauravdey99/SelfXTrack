"""Phase 5 device features: elderly fall / inactivity, BLE bus check-in, OTA firmware offers."""
import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import notify, push_msgs
from .config import settings
from .models import Bus, BusEvent, Device, DeviceBus, FirmwareRelease, SosEvent, User
from .realtime import manager
from .services import active_sos, as_utc, device_users, parent_users, sos_info


def _label(dev: Device) -> str:
    return dev.name or dev.device_id


# ---------------- elderly: fall ----------------
def handle_fall(db: Session, dev: Device, now: datetime) -> SosEvent | None:
    """Device detected a fall and the wearer did NOT cancel within 30 s -> SOS (reason: fall) to parents/carers.
    Works on every plan – it is an emergency."""
    if dev.fall_detection is False:
        return None
    sos = active_sos(db, dev)
    if sos is not None:
        return sos
    sos = SosEvent(device_pk=dev.id, lat=dev.last_lat, lon=dev.last_lon, started_at=now, source="fall")
    db.add(sos)
    db.flush()
    info = {**sos_info(dev, sos), "reason": "fall"}
    parents = parent_users(db, dev)
    notify.push(parents, "🆘 POSSIBLE FALL", f"{_label(dev)} may have fallen and did not cancel the alert.",
                {"type": "sos", **info})
    manager.publish([u.id for u in parents], {"type": "sos", **info})
    if len(parents) == len(device_users(db, dev)):
        sos.family_notified_at = now
    return sos


# ---------------- elderly: inactivity ----------------
def update_activity(dev: Device, act: int | None, now: datetime):
    if act is not None and act > 0:
        dev.last_active_at = now
        dev.inactivity_notified = False
    elif dev.last_active_at is None:
        dev.last_active_at = now


def _in_window(dev: Device, now: datetime) -> bool:
    from .ai import local
    m = local(now).hour * 60 + local(now).minute
    a = int(dev.active_from[:2]) * 60 + int(dev.active_from[3:])
    b = int(dev.active_to[:2]) * 60 + int(dev.active_to[3:])
    return a <= m <= b


def check_inactivity(db: Session, now: datetime | None = None) -> int:
    """Every minute: elderly tracker online but no movement for N hours during the day -> family alert.
    Guardian plan (spec); not an SOS."""
    from .plans import allows
    from .services_help import device_plan
    now = now or datetime.now(timezone.utc)
    n = 0
    for dev in db.scalars(select(Device).where(Device.claimed.is_(True), Device.kind == "elderly",
                                               Device.inactivity_notified.is_(False))).all():
        hrs = dev.inactivity_hours or 0
        if hrs <= 0 or dev.last_active_at is None or dev.last_seen is None:
            continue
        if as_utc(dev.last_seen) < now - timedelta(minutes=settings.offline_after_minutes):
            continue                                   # offline -> the offline alert covers it
        if not _in_window(dev, now) or not allows(device_plan(db, dev), "risk"):
            continue
        if as_utc(dev.last_active_at) <= now - timedelta(hours=hrs):
            dev.inactivity_notified = True
            from .ai import hhmm
            p = {"label": _label(dev), "hrs": hrs, "since": hhmm(dev.last_active_at)}
            users = device_users(db, dev)
            _, text = push_msgs.push(users, "inactivity", {"type": "ai_alert", "kind": "inactivity",
                                                           "device_id": dev.device_id, "text": "", "name": _label(dev)}, **p)
            _publish_text(users, "inactivity", {"type": "ai_alert", "kind": "inactivity", "device_id": dev.device_id}, p)
            from .models import AiAlert
            db.add(AiAlert(device_pk=dev.id, kind="inactivity", text=text, msg_args=push_msgs.args_json(**p),
                           lat=dev.last_lat, lon=dev.last_lon))
            n += 1
    db.commit()
    return n


# ---------------- BLE bus check-in ----------------
def bus_update(db: Session, dev: Device, seen: list[str] | None, now: datetime):
    """Beacon of a linked bus seen -> boarded; not seen in 2 reports in a row -> got off."""
    if seen is None:
        return
    links = db.scalars(select(Bus).join(DeviceBus, DeviceBus.bus_id == Bus.id).where(DeviceBus.device_pk == dev.id)).all()
    if not links:
        return
    seen_ids = {s.strip().upper() for s in seen}
    on = next((b for b in links if b.beacon_id.upper() in seen_ids), None)
    from .ai import hhmm, place_name
    where = place_name(db, dev, dev.last_lat, dev.last_lon) if dev.last_lat is not None else None
    near = "_near" if where else ""
    users = device_users(db, dev)
    if on and dev.on_bus_id != on.id:
        dev.on_bus_id, dev.bus_missed = on.id, 0
        db.add(BusEvent(device_pk=dev.id, bus_id=on.id, kind="board", lat=dev.last_lat, lon=dev.last_lon, ts=now))
        p = {"label": _label(dev), "bus": on.name, "time": hhmm(now), "place": where}
        push_msgs.push(users, "bus_on" + near, {"type": "bus", "device_id": dev.device_id, "text": ""}, **p)
        _publish_text(users, "bus_on" + near, {"type": "bus", "device_id": dev.device_id}, p)
    elif on:
        dev.bus_missed = 0
    elif dev.on_bus_id is not None:
        dev.bus_missed = (dev.bus_missed or 0) + 1
        if dev.bus_missed >= 2:
            bus = db.get(Bus, dev.on_bus_id)
            db.add(BusEvent(device_pk=dev.id, bus_id=dev.on_bus_id, kind="alight", lat=dev.last_lat, lon=dev.last_lon, ts=now))
            p = {"label": _label(dev), "bus": bus.name if bus else "🚌", "time": hhmm(now), "place": where}
            dev.on_bus_id, dev.bus_missed = None, 0
            push_msgs.push(users, "bus_off" + near, {"type": "bus", "device_id": dev.device_id, "text": ""}, **p)
            _publish_text(users, "bus_off" + near, {"type": "bus", "device_id": dev.device_id}, p)


def device_cfg(db: Session, dev: Device) -> dict:
    beacons = [b.beacon_id for b in db.scalars(select(Bus).join(DeviceBus, DeviceBus.bus_id == Bus.id)
                                                 .where(DeviceBus.device_pk == dev.id)).all()]
    return {"fall": bool(dev.fall_detection) and dev.kind == "elderly", "beacons": beacons}


# ---------------- OTA ----------------
def _bucket(device_id: str) -> int:
    return int(hashlib.sha256(device_id.encode()).hexdigest()[:8], 16) % 100


def _ver(v: str | None) -> tuple:
    out = []
    for part in (v or "0").replace("-", ".").split("."):
        out.append(int(part) if part.isdigit() else 0)
    return tuple(out)


def ota_offer(db: Session, dev: Device, sos_on: bool) -> dict | None:
    """Offer the newest active release of the device's channel if it is newer, in the rollout group,
    and safe to update now (no SOS, battery >= 30 % or charging)."""
    if sos_on or (dev.battery is not None and dev.battery < 30 and not dev.charging):
        return None
    rel = max(db.scalars(select(FirmwareRelease).where(FirmwareRelease.active.is_(True),
                                                       FirmwareRelease.channel == (dev.fw_channel or "stable"))).all(),
              key=lambda r: _ver(r.version), default=None)
    if rel is None or _ver(rel.version) <= _ver(dev.firmware) or _bucket(dev.device_id) >= rel.rollout_percent:
        return None
    return {"version": rel.version, "url": f"{settings.public_base_url.rstrip('/')}/api/device/firmware/{rel.id}",
            "sha256": rel.sha256, "size": rel.size}


def _publish_text(users, key: str, msg: dict, p: dict):
    """Live (WebSocket) copy of an alert, with the text in each user's language."""
    by_lang: dict[str, list[int]] = {}
    for u in users:
        by_lang.setdefault(getattr(u, "lang", None) or "en", []).append(u.id)
    for lang, ids in by_lang.items():
        manager.publish(ids, {**msg, "text": push_msgs.render(key, lang, **p)[1]})
