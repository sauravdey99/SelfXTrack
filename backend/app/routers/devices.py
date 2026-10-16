import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Device, DeviceMember, Location, SosEvent, User
from ..realtime import manager
from ..schemas import ClaimIn, DeviceOut, LocationOut, ProvisionIn, ProvisionOut, ShareIn, SosOut
from ..security import current_user, hash_secret, require_admin
from ..services import active_sos, device_users, end_share_links_for_sos, is_online, school_staff_users

router = APIRouter(prefix="/api", tags=["devices"])


def _get_member_device(db: Session, user: User, device_id: str) -> Device:
    dev = db.scalar(select(Device).where(Device.device_id == device_id))
    if dev is None or not any(m.user_id == user.id for m in dev.members):
        raise HTTPException(404, "Device not found")
    return dev


def _device_out(db: Session, dev: Device) -> DeviceOut:
    out = DeviceOut.model_validate(dev)
    out.online = is_online(dev)
    sos = active_sos(db, dev)
    out.active_sos = sos.id if sos else None
    return out


# ---- Factory provisioning (admin) ----
@router.post("/admin/devices", response_model=ProvisionOut, dependencies=[Depends(require_admin)])
def provision(body: ProvisionIn, db: Session = Depends(get_db)):
    if db.scalar(select(Device).where(Device.device_id == body.device_id)):
        raise HTTPException(409, "Device already exists")
    secret = secrets.token_urlsafe(24)
    claim = secrets.token_hex(3).upper()  # 6 chars, printed on the card in the box
    db.add(Device(device_id=body.device_id, secret_hash=hash_secret(secret), claim_code=claim, kind=body.kind))
    db.commit()
    return ProvisionOut(device_id=body.device_id, device_secret=secret, claim_code=claim)


@router.post("/admin/devices/{device_id}/secret", response_model=ProvisionOut, dependencies=[Depends(require_admin)])
def reset_secret(device_id: str, db: Session = Depends(get_db)):
    """Factory / test tool: issue a NEW device secret (old one stops working). Claim + family stay."""
    dev = db.scalar(select(Device).where(Device.device_id == device_id))
    if dev is None:
        raise HTTPException(404, "Device not found")
    secret = secrets.token_urlsafe(24)
    dev.secret_hash = hash_secret(secret)
    db.commit()
    return ProvisionOut(device_id=dev.device_id, device_secret=secret, claim_code=dev.claim_code)


# ---- Parent app ----
@router.post("/devices/claim", response_model=DeviceOut)
def claim(body: ClaimIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = db.scalar(select(Device).where(Device.device_id == body.device_id.strip()))
    if dev is None or dev.claim_code != body.claim_code.strip().upper():
        raise HTTPException(400, "Device ID or claim code is wrong")
    if dev.claimed:
        raise HTTPException(409, "Device already registered. Ask the owner to share it with you.")
    dev.claimed, dev.name, dev.kind = True, body.name.strip(), body.kind
    db.add(DeviceMember(device_pk=dev.id, user_id=user.id, role="owner"))
    # family is shared: everyone already in my family gets this new child too
    mine = db.scalars(select(DeviceMember.device_pk).where(DeviceMember.user_id == user.id, DeviceMember.role == "owner")).all()
    fam = {m.user_id: m.role for m in db.scalars(select(DeviceMember).where(DeviceMember.device_pk.in_(mine),
                                                                             DeviceMember.role.in_(["family", "parent"]))).all()}
    for uid, role in fam.items():
        if uid != user.id:
            db.add(DeviceMember(device_pk=dev.id, user_id=uid, role=role))
    db.commit()
    db.refresh(dev)
    return _device_out(db, dev)


@router.post("/devices/{device_id}/share")
def share(device_id: str, body: ShareIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    if not any(m.user_id == user.id and m.role == "owner" for m in dev.members):
        raise HTTPException(403, "Only the owner can share")
    other = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if other is None:
        raise HTTPException(404, "That person must register in the app first")
    if not any(m.user_id == other.id for m in dev.members):
        db.add(DeviceMember(device_pk=dev.id, user_id=other.id, role="family"))
        db.commit()
    return {"ok": True}


@router.get("/devices", response_model=list[DeviceOut])
def my_devices(user: User = Depends(current_user), db: Session = Depends(get_db)):
    devs = db.scalars(select(Device).join(DeviceMember).where(DeviceMember.user_id == user.id)).all()
    return [_device_out(db, d) for d in devs]


@router.get("/devices/{device_id}", response_model=DeviceOut)
def device_detail(device_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _device_out(db, _get_member_device(db, user, device_id))


@router.get("/devices/{device_id}/history", response_model=list[LocationOut])
def history(device_id: str, hours: int = Query(24, ge=1, le=24 * 90), today: bool = False,
            user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    from ..plans import PLANS
    from ..services_help import device_plan
    hours = min(hours, PLANS[device_plan(db, dev)]["history_days"] * 24)   # Basic: 7 days, Smart/Guardian: 90
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    if today:                                  # live map: today's path only (from local midnight)
        from zoneinfo import ZoneInfo
        from ..config import settings
        tz = ZoneInfo(settings.local_timezone)
        since = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    return db.scalars(select(Location).where(Location.device_pk == dev.id, Location.ts >= since)
                      .order_by(Location.ts.asc()).limit(5000)).all()


# ---- SOS ----
def _sos_out(ev: SosEvent, dev: Device) -> SosOut:
    out = SosOut.model_validate(ev)
    out.device_id, out.device_name = dev.device_id, dev.name
    who_id = ev.acknowledged_by or getattr(ev, "escalated_by", None)
    if who_id:
        from sqlalchemy.orm import object_session
        u = object_session(ev).get(User, who_id)
        if u:
            fam = any(m.user_id == u.id for m in dev.members)
            out.responder = f"{u.name} ({'family' if fam else 'school'})"
    return out


@router.get("/sos", response_model=list[SosOut])
def list_sos(active_only: bool = True, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(SosEvent, Device).join(Device, SosEvent.device_pk == Device.id).join(DeviceMember).where(
        DeviceMember.user_id == user.id)
    if active_only:
        q = q.where(SosEvent.status.in_(["active", "acknowledged"]))
    rows = db.execute(q.order_by(SosEvent.started_at.desc()).limit(100)).all()
    return [_sos_out(ev, dev) for ev, dev in rows]


def _change_sos(db: Session, user: User, sos_id: int, status: str) -> SosOut:
    ev = db.get(SosEvent, sos_id)
    if ev is None:
        raise HTTPException(404, "SOS not found")
    dev = db.get(Device, ev.device_pk)
    is_family = any(m.user_id == user.id for m in dev.members)
    is_staff = any(s.id == user.id for s in school_staff_users(db, dev))
    if not (is_family or (is_staff and status == "acknowledged")):
        raise HTTPException(404, "SOS not found")
    now = datetime.now(timezone.utc)
    if status == "acknowledged" and ev.status == "active":
        ev.status, ev.acknowledged_by, ev.acknowledged_at = "acknowledged", user.id, now
    elif status in ("resolved", "cancelled"):
        ev.status, ev.resolved_at = status, now
        end_share_links_for_sos(db, ev)   # stop any live links created for this emergency
        from ..services_help import close_help
        close_help(db, ev)                 # tell helpers, stop their access
    db.commit()
    manager.publish([u.id for u in device_users(db, dev)] + [s.id for s in school_staff_users(db, dev)],
                    {"type": "sos_update", "sos_id": ev.id, "device_id": dev.device_id, "status": ev.status,
                     "by": user.name})
    return _sos_out(ev, dev)


@router.post("/sos/{sos_id}/acknowledge", response_model=SosOut)
def ack(sos_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _change_sos(db, user, sos_id, "acknowledged")


@router.post("/sos/{sos_id}/resolve", response_model=SosOut)
def resolve(sos_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Family marks the child safe."""
    return _change_sos(db, user, sos_id, "resolved")
