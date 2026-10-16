import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import notify
from .config import settings
from .models import Device, DeviceSchool, Geofence, Location, SchoolStaff, ShareLink, SosEvent, User
from .realtime import manager
from .schemas import TelemetryIn


def as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def distance_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def device_users(db: Session, dev: Device) -> list[User]:
    """Family members of the device."""
    return [m.user for m in dev.members]


def parent_users(db: Session, dev: Device) -> list[User]:
    """Step 1 of a child SOS: the parent(s) who own the tracker."""
    return [m.user for m in dev.members if m.role in ("owner", "parent")] or [m.user for m in dev.members]


def school_staff_users(db: Session, dev: Device) -> list[User]:
    """School staff who receive this child's SOS (only where the parent gave consent)."""
    rows = db.scalars(
        select(User).join(SchoolStaff, SchoolStaff.user_id == User.id)
        .join(DeviceSchool, DeviceSchool.school_id == SchoolStaff.school_id)
        .where(DeviceSchool.device_pk == dev.id, DeviceSchool.share_sos.is_(True), SchoolStaff.status == "approved")
    ).all()
    return list(rows)


def active_sos(db: Session, dev: Device) -> SosEvent | None:
    return db.scalar(
        select(SosEvent)
        .where(SosEvent.device_pk == dev.id, SosEvent.status.in_(["active", "acknowledged"]))
        .order_by(SosEvent.started_at.desc())
    )


def is_online(dev: Device) -> bool:
    last = as_utc(dev.last_seen)
    return last is not None and datetime.now(timezone.utc) - last < timedelta(minutes=settings.offline_after_minutes)


def report_interval(dev: Device, sos_on: bool, moving_fast: bool) -> int:
    """Server tells the device how often to report (battery vs. freshness)."""
    if sos_on:
        return 10
    if moving_fast:
        return 60
    return 300


def sos_info(dev: Device, ev: SosEvent | None = None) -> dict:
    """Emergency info pack shared with family / school / helpers."""
    return {
        "device_id": dev.device_id, "name": dev.name or dev.device_id,
        "sos_id": ev.id if ev else None,
        "started_at": as_utc(ev.started_at).isoformat() if ev else None,
        "lat": dev.last_lat, "lon": dev.last_lon, "accuracy_m": dev.last_accuracy,
        "speed_kmh": dev.last_speed, "heading_deg": dev.last_heading,
        "battery": dev.battery, "last_seen": as_utc(dev.last_seen).isoformat() if dev.last_seen else None,
    }


def _check_geofences(db: Session, dev: Device, users: list[User], lat: float, lon: float, acc: float | None) -> None:
    label = dev.name or dev.device_id
    for g in db.scalars(select(Geofence).where(Geofence.device_pk == dev.id)).all():
        d = distance_m(lat, lon, g.lat, g.lon)
        margin = min(acc or 0, 50)          # hysteresis so GPS jitter does not flap
        if d <= g.radius_m - margin * 0.5:
            now_inside = True
        elif d >= g.radius_m + margin:
            now_inside = False
        else:
            continue
        if g.inside is None:
            g.inside = now_inside            # first fix: set state silently
            continue
        if now_inside != g.inside:
            g.inside = now_inside
            if now_inside and g.notify_enter:
                title, body, kind = f"✅ {label} reached {g.name}", f"{label} arrived at {g.name}.", "geofence_enter"
            elif not now_inside and g.notify_exit:
                title, body, kind = f"{label} left {g.name}", f"{label} has left {g.name}.", "geofence_exit"
            else:
                if not now_inside:
                    from . import places
                    places.on_exit(db, dev, g)       # left during its time slot, before the end?
                continue
            if not now_inside:
                from . import places
                places.on_exit(db, dev, g)
            notify.push(users, title, body, {"type": kind, "device_id": dev.device_id, "geofence": g.name})
            manager.publish([u.id for u in users], {"type": kind, "device_id": dev.device_id, "geofence": g.name,
                                                    "name": label})


def ingest_telemetry(db: Session, dev: Device, p: TelemetryIn) -> tuple[int, bool]:
    now = datetime.now(timezone.utc)
    ts = datetime.fromtimestamp(p.t, tz=timezone.utc) if p.t else now
    if ts > now + timedelta(minutes=5):  # bad device clock
        ts = now

    users = device_users(db, dev)
    user_ids = [u.id for u in users]
    label = dev.name or dev.device_id

    # back online after an offline alert
    if dev.offline_notified:
        dev.offline_notified = False
        notify.push(users, f"{label} is back online", f"{label}'s tracker is connected again.",
                    {"type": "online", "device_id": dev.device_id})

    dev.last_seen = now
    if p.bat is not None:
        dev.battery = p.bat
    dev.charging = bool(p.chg)
    if p.fw:
        dev.firmware = p.fw

    if p.lat is not None and p.lon is not None:
        dev.last_lat, dev.last_lon, dev.last_accuracy = p.lat, p.lon, p.acc
        dev.last_speed, dev.last_heading = p.spd, p.hdg
        db.add(Location(device_pk=dev.id, ts=ts, lat=p.lat, lon=p.lon, accuracy=p.acc,
                        speed=p.spd, heading=p.hdg, battery=p.bat, source=p.src or "gnss"))
        manager.publish(user_ids, {"type": "location", "device_id": dev.device_id, "lat": p.lat,
                                   "lon": p.lon, "acc": p.acc, "spd": p.spd, "hdg": p.hdg,
                                   "bat": p.bat, "ts": ts.isoformat()})
        _check_geofences(db, dev, users, p.lat, p.lon, p.acc)

    # Low battery alert (once until recharged above threshold + 5)
    if dev.battery is not None:
        if dev.battery <= settings.low_battery_percent and not dev.low_battery_notified and not dev.charging:
            dev.low_battery_notified = True
            notify.push(users, "Low battery", f"{label}'s tracker battery is {dev.battery}%.",
                        {"type": "low_battery", "device_id": dev.device_id})
            manager.publish(user_ids, {"type": "low_battery", "device_id": dev.device_id, "bat": dev.battery})
        elif dev.battery > settings.low_battery_percent + 5:
            dev.low_battery_notified = False

    # Phase 5: elderly activity / fall, BLE bus check-in
    from . import services_p5
    services_p5.update_activity(dev, p.act, now)
    services_p5.bus_update(db, dev, p.ble, now)
    if p.fall and not p.sos:
        services_p5.handle_fall(db, dev, now)

    # SOS -> family + school circle (consented)
    sos = active_sos(db, dev)
    if p.sos and sos is None:
        sos = SosEvent(device_pk=dev.id, lat=dev.last_lat, lon=dev.last_lon, started_at=now)
        db.add(sos)
        db.flush()
        info = sos_info(dev, sos)
        # D5: parents first. School is alerted by the parent ("Emergency – School") or automatically
        # after settings.sos_school_escalation_seconds if no parent responds (see services_help.check_escalations).
        # Escalation ladder: parents now -> other family after 2 min -> school after 5 min (if nobody responds)
        parents = parent_users(db, dev)
        notify.push(parents, "🚨 SOS ALERT", f"{label} has pressed the SOS button.", {"type": "sos", **info})
        manager.publish([u.id for u in parents], {"type": "sos", **info})
        if len(parents) == len(users):
            sos.family_notified_at = now        # no other family members
    elif sos is not None:
        if sos.lat is None and dev.last_lat is not None:
            sos.lat, sos.lon = dev.last_lat, dev.last_lon
        if p.lat is not None and sos.school_notified_at is not None:  # live SOS updates to school staff
            manager.publish([s.id for s in school_staff_users(db, dev)], {"type": "sos_location", **sos_info(dev, sos)})

    # Phase 4 AI (advisory only, Smart+ plans, never during an SOS)
    if sos is None and p.lat is not None:
        try:
            from . import ai
            from .plans import allows
            from .services_help import device_plan
            plan = device_plan(db, dev)
            if allows(plan, "ai"):
                ai.check(db, dev, users, p.lat, p.lon, p.spd, ts, plan)
        except Exception as e:   # AI must never break telemetry / SOS
            import logging
            logging.getLogger("selfx.ai").warning("ai check failed: %s", e)

    db.commit()
    sos_on = sos is not None
    interval = report_interval(dev, sos_on, (p.spd or 0) > 10)
    return interval, sos_on


def end_share_links_for_sos(db: Session, sos: SosEvent) -> None:
    for link in db.scalars(select(ShareLink).where(ShareLink.sos_id == sos.id, ShareLink.revoked.is_(False))).all():
        link.revoked = True


def check_offline(db: Session) -> int:
    """Alert families when a tracker stops reporting. Called every minute by a background task."""
    limit = datetime.now(timezone.utc) - timedelta(minutes=settings.offline_after_minutes)
    count = 0
    for dev in db.scalars(select(Device).where(Device.claimed.is_(True), Device.offline_notified.is_(False),
                                               Device.last_seen.is_not(None))).all():
        if as_utc(dev.last_seen) < limit:
            dev.offline_notified = True
            users = device_users(db, dev)
            label = dev.name or dev.device_id
            batt = f" Last battery {dev.battery}%." if dev.battery is not None else ""
            notify.push(users, f"{label}'s tracker is offline",
                        f"No update for {settings.offline_after_minutes} min.{batt}",
                        {"type": "offline", "device_id": dev.device_id})
            manager.publish([u.id for u in users], {"type": "offline", "device_id": dev.device_id})
            count += 1
    db.commit()
    return count
