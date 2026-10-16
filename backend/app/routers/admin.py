"""Admin / operations API (header X-Admin-Key). Used by the /admin web panel and factory tools.
Firmware releases (OTA), devices, users, plans, bans, abuse reports, overview numbers."""
import hashlib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AbuseReport, Device, DeviceMember, FirmwareRelease, SosEvent, User
from ..plans import PLANS, effective_plan
from ..security import require_admin
from ..services import as_utc

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])
FW_DIR = Path(__file__).resolve().parents[2] / "data" / "firmware"


def _iso(dt):
    return as_utc(dt).isoformat() if dt else None


# ---------------- overview ----------------
@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    online = now - timedelta(minutes=30)
    plans = {p: 0 for p in PLANS}
    for u in db.scalars(select(User)).all():
        plans[effective_plan(u)] = plans.get(effective_plan(u), 0) + 1
    return {
        "users": db.scalar(select(func.count(User.id))), "plans": plans,
        "devices": db.scalar(select(func.count(Device.id))),
        "claimed": db.scalar(select(func.count(Device.id)).where(Device.claimed.is_(True))),
        "online": db.scalar(select(func.count(Device.id)).where(Device.last_seen >= online)),
        "active_sos": db.scalar(select(func.count(SosEvent.id)).where(SosEvent.status.in_(["active", "acknowledged"]))),
        "sos_7d": db.scalar(select(func.count(SosEvent.id)).where(SosEvent.started_at >= now - timedelta(days=7))),
        "reports": db.scalar(select(func.count(AbuseReport.id))),
    }


# ---------------- devices ----------------
@router.get("/devices")
def devices(q: str = "", db: Session = Depends(get_db)):
    out = []
    for d in db.scalars(select(Device).order_by(Device.id.desc()).limit(500)).all():
        owner = next((m.user for m in d.members if m.role == "owner"), None)
        if q and q.lower() not in f"{d.device_id} {d.name} {owner.email if owner else ''}".lower():
            continue
        out.append({"device_id": d.device_id, "name": d.name, "kind": d.kind, "claimed": d.claimed,
                    "owner": owner.email if owner else None, "battery": d.battery, "last_seen": _iso(d.last_seen),
                    "firmware": d.firmware, "fw_channel": d.fw_channel, "ota_status": d.ota_status,
                    "members": len(d.members)})
    return out


class ChannelIn(BaseModel):
    channel: str


@router.put("/devices/{device_id}/channel")
def set_channel(device_id: str, body: ChannelIn, db: Session = Depends(get_db)):
    d = db.scalar(select(Device).where(Device.device_id == device_id))
    if d is None:
        raise HTTPException(404, "Device not found")
    d.fw_channel = "beta" if body.channel == "beta" else "stable"
    db.commit()
    return {"ok": True, "channel": d.fw_channel}


# ---------------- users ----------------
@router.get("/users")
def users(q: str = "", db: Session = Depends(get_db)):
    out = []
    for u in db.scalars(select(User).order_by(User.id.desc()).limit(500)).all():
        if q and q.lower() not in f"{u.email} {u.name} {u.phone}".lower():
            continue
        out.append({"id": u.id, "email": u.email, "name": u.name, "phone": u.phone, "verified": u.phone_verified,
                    "plan": effective_plan(u), "plan_status": u.plan_status, "expires": _iso(u.plan_expires_at),
                    "banned": u.banned, "devices": len(u.memberships)})
    return out


class BanIn(BaseModel):
    banned: bool


@router.put("/users/{user_id}/ban")
def ban(user_id: int, body: BanIn, db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "User not found")
    u.banned = body.banned
    db.commit()
    return {"ok": True}


@router.get("/reports")
def reports(db: Session = Depends(get_db)):
    out = []
    for r in db.scalars(select(AbuseReport).order_by(AbuseReport.id.desc()).limit(200)).all():
        a, b = db.get(User, r.reporter_id), db.get(User, r.reported_user_id)
        out.append({"id": r.id, "reporter": a.email if a else None, "reported": b.email if b else None,
                    "reported_id": r.reported_user_id, "banned": b.banned if b else None, "reason": r.reason,
                    "sos_id": r.sos_id, "at": _iso(r.created_at)})
    return out


# ---------------- firmware (OTA) ----------------
@router.post("/firmware")
async def upload_firmware(request: Request, version: str = Query(..., pattern=r"^[0-9][0-9A-Za-z.\-]{0,30}$"),
                          channel: str = "stable", rollout: int = Query(100, ge=1, le=100), notes: str = "",
                          db: Session = Depends(get_db)):
    """Body = raw .bin image (Content-Type: application/octet-stream). Signed builds only in production."""
    data = await request.body()
    if len(data) < 1024:
        raise HTTPException(400, "Firmware image is empty or too small")
    if data[0] != 0xE9:                       # ESP32 app image magic byte
        raise HTTPException(400, "Not an ESP32 app image (first byte must be 0xE9)")
    FW_DIR.mkdir(parents=True, exist_ok=True)
    name = f"selfx-{re.sub(r'[^0-9A-Za-z.-]', '', version)}-{channel}.bin"
    (FW_DIR / name).write_bytes(data)
    rel = FirmwareRelease(version=version, channel="beta" if channel == "beta" else "stable", filename=name,
                          sha256=hashlib.sha256(data).hexdigest(), size=len(data), rollout_percent=rollout,
                          notes=notes[:500] or None)
    db.add(rel)
    db.commit()
    return _rel(rel)


def _rel(r: FirmwareRelease) -> dict:
    return {"id": r.id, "version": r.version, "channel": r.channel, "size": r.size, "sha256": r.sha256,
            "rollout_percent": r.rollout_percent, "active": r.active, "notes": r.notes, "created_at": _iso(r.created_at)}


@router.get("/firmware")
def list_firmware(db: Session = Depends(get_db)):
    rels = db.scalars(select(FirmwareRelease).order_by(FirmwareRelease.id.desc())).all()
    counts = {}
    for d in db.scalars(select(Device)).all():
        counts[d.firmware or "unknown"] = counts.get(d.firmware or "unknown", 0) + 1
    return {"releases": [_rel(r) for r in rels], "devices_by_version": counts}


class ReleaseIn(BaseModel):
    active: bool | None = None
    rollout_percent: int | None = None


@router.put("/firmware/{rid}")
def update_release(rid: int, body: ReleaseIn, db: Session = Depends(get_db)):
    """Pause a bad release (active=false) or widen the rollout."""
    r = db.get(FirmwareRelease, rid)
    if r is None:
        raise HTTPException(404, "Release not found")
    if body.active is not None:
        r.active = body.active
    if body.rollout_percent is not None:
        r.rollout_percent = max(1, min(100, body.rollout_percent))
    db.commit()
    return _rel(r)
