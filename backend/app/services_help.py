"""Phase 3: Emergency – School, Emergency – Group (nearby helpers), escalation, plan rules."""
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import notify
from .config import settings
from .models import (Device, DeviceMember, HelpRequest, HelperResponse, ShareLink, SosEvent, TeacherContact,
                     User)
from .realtime import manager
from .services import as_utc, device_users, distance_m, school_staff_users, sos_info
from .sms import send_sms

from .plans import FEATURE_MIN_PLAN, PLAN_RANK, allows, effective_plan  # noqa: F401


def device_plan(db: Session, dev: Device) -> str:
    """Plan of the tracker = best (effective) plan among its owners."""
    plans = [effective_plan(m.user) for m in dev.members if m.role == "owner"] or ["basic"]
    return max(plans, key=lambda p: PLAN_RANK.get(p, 0))


def plan_allows(db: Session, dev: Device, feature: str) -> bool:
    return allows(device_plan(db, dev), feature)


def ensure_sos(db: Session, dev: Device, by_user: User) -> SosEvent:
    """Parent escalation without a device SOS (e.g. after a safe-zone exit) creates a parent SOS."""
    from .services import active_sos
    sos = active_sos(db, dev)
    if sos is None:
        sos = SosEvent(device_pk=dev.id, lat=dev.last_lat, lon=dev.last_lon, source="parent",
                       status="acknowledged", acknowledged_by=by_user.id,
                       acknowledged_at=datetime.now(timezone.utc))
        db.add(sos)
        db.flush()
        # The parent who pressed the button already sees the emergency screen -> no alarm for them.
        # Other family members get a quiet heads-up (not the loud SOS alarm: the child did not press SOS).
        others = [u for u in device_users(db, dev) if u.id != by_user.id]
        manager.publish([u.id for u in others], {"type": "family_escalated", "sos_id": sos.id,
                                                 "device_id": dev.device_id, "name": dev.name or dev.device_id,
                                                 "by": by_user.name})
    return sos


def _sos_link(db: Session, dev: Device, sos: SosEvent, by_user_id: int) -> str:
    link = ShareLink(device_pk=dev.id, token=secrets.token_urlsafe(16), created_by=by_user_id, sos_id=sos.id,
                     expires_at=datetime.now(timezone.utc) + timedelta(hours=3))
    db.add(link)
    db.flush()
    return f"{settings.public_base_url.rstrip('/')}/live/{link.token}"


def school_contacts(db: Session, dev: Device) -> list[TeacherContact]:
    """People to alert for Emergency – School: contacts of school places + older contacts not linked to a place.
    A swimming coach or tutor is NOT alerted for a school emergency."""
    from .models import Geofence
    school_ids = {g.id for g in db.scalars(select(Geofence).where(Geofence.device_pk == dev.id,
                                                                   Geofence.kind == "school")).all()}
    return [c for c in db.scalars(select(TeacherContact).where(TeacherContact.device_pk == dev.id)).all()
            if c.place_id is None or c.place_id in school_ids]


def escalate_school(db: Session, dev: Device, sos: SosEvent, by_user: User | None) -> dict:
    """Emergency – School: approved staff of linked schools + teacher contacts added by the parent."""
    from .places import alerted_keys
    if "school" in alerted_keys(sos):
        return {"already": True, "staff": 0, "contacts": 0}
    sos.school_notified_at = sos.school_notified_at or datetime.now(timezone.utc)
    from .places import mark_alerted
    mark_alerted(sos, "school")
    if by_user:
        sos.escalated_by = by_user.id
    label = dev.name or dev.device_id
    info = sos_info(dev, sos)
    family = {u.id for u in device_users(db, dev)}
    staff = [u for u in school_staff_users(db, dev) if u.id not in family]
    who = f" (requested by {by_user.name})" if by_user else " (no parent response)"
    notify.push(staff, "🚨 Student emergency", f"Student {label} needs help{who}.", {"type": "sos", "role": "school", "by": by_user.name if by_user else "", **info})
    manager.publish([s.id for s in staff], {"type": "sos", "role": "school", "by": by_user.name if by_user else "", **info})
    contacts = school_contacts(db, dev)
    if contacts:
        url = _sos_link(db, dev, sos, by_user.id if by_user else dev.members[0].user_id)
        for c in contacts:
            send_sms(c.phone, f"EMERGENCY: {label} needs help{who}. Live location: {url} . Call 112 if needed.")
        # contacts who also use the SelfXTrack app (verified phone) get the full in-app alert too
        app_users = [u for u in db.scalars(select(User).where(User.phone.in_([c.phone for c in contacts]),
                                                               User.phone_verified.is_(True))).all()
                     if u.id not in {s.id for s in staff} and u.id not in family]
        if app_users:
            notify.push(app_users, "🚨 Student emergency", f"Student {label} needs help{who}.", {"type": "sos", "role": "school", "by": by_user.name if by_user else "", **info})
            manager.publish([u.id for u in app_users], {"type": "sos", "role": "school", "by": by_user.name if by_user else "", **info})
    db.commit()
    manager.publish([u.id for u in device_users(db, dev) if not by_user or u.id != by_user.id],
                    {"type": "school_escalated", "sos_id": sos.id, "device_id": dev.device_id,
                     "staff": len(staff), "contacts": len(contacts)})
    return {"already": False, "staff": len(staff), "contacts": len(contacts)}


def _eligible_helpers(db: Session, dev: Device, lat: float, lon: float, radius: int, exclude: set[int]) -> list[tuple[User, float]]:
    since = datetime.now(timezone.utc) - timedelta(minutes=settings.helper_location_max_age_minutes)
    family = {m.user_id for m in dev.members}
    out = []
    for u in db.scalars(select(User).where(User.phone_verified.is_(True), User.banned.is_(False),
                                           User.helper_available.is_(True), User.helper_lat.is_not(None))).all():
        if u.id in family or u.id in exclude or as_utc(u.helper_loc_at) < since:
            continue
        d = distance_m(lat, lon, u.helper_lat, u.helper_lon)
        if d <= radius:
            out.append((u, d))
    return out


def _notify_helpers(db: Session, hr: HelpRequest, dev: Device) -> int:
    if dev.last_lat is None:
        return 0
    already = {r.user_id for r in db.scalars(select(HelperResponse).where(HelperResponse.help_id == hr.id)).all()}
    helpers = _eligible_helpers(db, dev, dev.last_lat, dev.last_lon, hr.radius_m, already)
    for u, d in helpers:
        db.add(HelperResponse(help_id=hr.id, user_id=u.id))
        approx = int(round(d / 100.0) * 100) or 100
        # Level 1: no name, no exact location
        data = {"type": "help_request", "help_id": hr.id, "distance_m": approx}
        notify.push([u], "🆘 Help needed nearby", f"A child needs help about {approx} m from you. Can you help?", data)
        manager.publish([u.id], data)
    db.commit()
    return len(helpers)


def start_group(db: Session, dev: Device, sos: SosEvent, by_user: User) -> dict:
    if sos.escalated_by is None:
        sos.escalated_by = by_user.id
    hr = db.scalar(select(HelpRequest).where(HelpRequest.sos_id == sos.id, HelpRequest.closed.is_(False)))
    if hr is None:
        hr = HelpRequest(sos_id=sos.id, requested_by=by_user.id, radius_m=settings.group_radius_m)
        db.add(hr)
        db.flush()
    n = _notify_helpers(db, hr, dev)
    manager.publish([u.id for u in device_users(db, dev) if u.id != by_user.id],
                    {"type": "group_started", "sos_id": sos.id, "device_id": dev.device_id, "notified": n,
                     "radius_m": hr.radius_m})
    return {"help_id": hr.id, "notified": n, "radius_m": hr.radius_m}


def close_help(db: Session, sos: SosEvent) -> None:
    for hr in db.scalars(select(HelpRequest).where(HelpRequest.sos_id == sos.id, HelpRequest.closed.is_(False))).all():
        hr.closed = True
        users = [db.get(User, r.user_id) for r in
                 db.scalars(select(HelperResponse).where(HelperResponse.help_id == hr.id)).all()]
        notify.push(users, "✅ Child is safe", "Thank you – the family has marked the child safe.",
                    {"type": "help_closed", "help_id": hr.id})
        manager.publish([u.id for u in users], {"type": "help_closed", "help_id": hr.id})


def check_escalations(db: Session) -> None:
    """Every minute: auto-escalate to school after D5 timeout; widen group radius after D8 timeout."""
    now = datetime.now(timezone.utc)
    # step 2: parents did not respond -> ring the rest of the family
    for sos in db.scalars(select(SosEvent).where(SosEvent.status == "active", SosEvent.source.in_(["device", "fall"]),
                                                SosEvent.family_notified_at.is_(None))).all():
        if now - as_utc(sos.started_at) >= timedelta(seconds=settings.sos_family_escalation_seconds):
            from .services import parent_users
            dev = db.get(Device, sos.device_pk)
            sos.family_notified_at = now
            pids = {u.id for u in parent_users(db, dev)}
            others = [u for u in device_users(db, dev) if u.id not in pids]
            info = sos_info(dev, sos)
            mins = int((now - as_utc(sos.started_at)).total_seconds() // 60)
            what = "may have fallen" if sos.source == "fall" else "pressed SOS"
            notify.push(others, "🚨 SOS ALERT", f"{dev.name or dev.device_id} {what} {mins} min ago – parents have "
                        "not responded yet.", {"type": "sos", **info})
            manager.publish([u.id for u in others], {"type": "sos", **info})
    # step 3: still nobody responded -> school
    for sos in db.scalars(select(SosEvent).where(SosEvent.status == "active", SosEvent.school_notified_at.is_(None))).all():
        if now - as_utc(sos.started_at) >= timedelta(seconds=settings.sos_school_escalation_seconds):
            dev = db.get(Device, sos.device_pk)
            if not plan_allows(db, dev, "school"):
                sos.school_notified_at = now   # mark as handled (Basic plan: parents only)
                continue
            # the people responsible right now: coach at swimming, tutor at tuition … – else the school
            from . import places
            from .models import Geofence
            ctx = places.current_context(db, dev, now)
            g = db.get(Geofence, ctx["place"]["id"]) if ctx.get("place") else None
            if g is not None and g.kind != "school" and places.people(db, g):
                places.escalate_place(db, dev, sos, None, g)
            elif dev.kind != "elderly":
                escalate_school(db, dev, sos, None)
            else:
                sos.school_notified_at = now
    for hr in db.scalars(select(HelpRequest).where(HelpRequest.closed.is_(False), HelpRequest.expanded_at.is_(None))).all():
        if now - as_utc(hr.created_at) < timedelta(seconds=settings.group_expand_after_seconds):
            continue
        accepted = db.scalar(select(HelperResponse).where(HelperResponse.help_id == hr.id, HelperResponse.status == "accepted"))
        if accepted is None:
            hr.radius_m, hr.expanded_at = settings.group_expand_radius_m, now
            sos = db.get(SosEvent, hr.sos_id)
            dev = db.get(Device, sos.device_pk)
            n = _notify_helpers(db, hr, dev)
            manager.publish([u.id for u in device_users(db, dev)],
                            {"type": "group_expanded", "sos_id": sos.id, "notified": n, "radius_m": hr.radius_m})
    db.commit()
