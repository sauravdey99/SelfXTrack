"""Phase 5 (parent side): school bus beacons, elderly-care settings, bus history."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Bus, BusEvent, Device, DeviceBus, DeviceMember, User
from ..security import current_user
from ..services import as_utc
from .devices import _get_member_device

router = APIRouter(prefix="/api", tags=["phase5"])


def _my_owned(db: Session, user: User) -> list[Device]:
    return list(db.scalars(select(Device).join(DeviceMember, DeviceMember.device_pk == Device.id)
                           .where(DeviceMember.user_id == user.id, DeviceMember.role == "owner")).all())


def _buses(db: Session, dev: Device) -> list[dict]:
    rows = db.scalars(select(Bus).join(DeviceBus, DeviceBus.bus_id == Bus.id).where(DeviceBus.device_pk == dev.id)).all()
    return [{"id": b.id, "name": b.name, "beacon_id": b.beacon_id, "on_now": dev.on_bus_id == b.id} for b in rows]


@router.get("/devices/{device_id}/buses")
def list_buses(device_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _buses(db, _get_member_device(db, user, device_id))


class BusIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    beacon_id: str = Field(min_length=3, max_length=64)
    all_children: bool = False


@router.post("/devices/{device_id}/buses")
def add_bus(device_id: str, body: BusIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Link the school bus (BLE beacon ID printed on the beacon) – the tracker then reports boarding / getting off."""
    dev = _get_member_device(db, user, device_id)
    bid = body.beacon_id.strip().upper()
    bus = db.scalar(select(Bus).where(Bus.beacon_id == bid))
    if bus is None:
        bus = Bus(name=body.name.strip(), beacon_id=bid, created_by=user.id)
        db.add(bus)
        db.flush()
    from ..models import Transport
    for d in (_my_owned(db, user) if body.all_children else [dev]):
        if db.scalar(select(DeviceBus).where(DeviceBus.device_pk == d.id, DeviceBus.bus_id == bus.id)) is None:
            db.add(DeviceBus(device_pk=d.id, bus_id=bus.id))
        if db.scalar(select(Transport).where(Transport.device_pk == d.id, Transport.bus_id == bus.id)) is None:
            db.add(Transport(device_pk=d.id, name=bus.name, kind="bus", bus_id=bus.id, created_by=user.id))
    db.commit()
    return _buses(db, dev)


@router.delete("/devices/{device_id}/buses/{bus_id}")
def remove_bus(device_id: str, bus_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    link = db.scalar(select(DeviceBus).where(DeviceBus.device_pk == dev.id, DeviceBus.bus_id == bus_id))
    from ..models import Transport
    for t in db.scalars(select(Transport).where(Transport.device_pk == dev.id, Transport.bus_id == bus_id)).all():
        db.delete(t)
    if link:
        db.delete(link)
        if dev.on_bus_id == bus_id:
            dev.on_bus_id = None
    db.commit()
    return _buses(db, dev)


@router.get("/devices/{device_id}/bus-events")
def bus_events(device_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..ai import local
    dev = _get_member_device(db, user, device_id)
    out = []
    for e in db.scalars(select(BusEvent).where(BusEvent.device_pk == dev.id).order_by(BusEvent.ts.desc()).limit(50)).all():
        b = db.get(Bus, e.bus_id)
        out.append({"kind": e.kind, "bus": b.name if b else None, "at": local(e.ts).strftime("%a %d %b %H:%M"),
                    "lat": e.lat, "lon": e.lon})
    return out


class CareIn(BaseModel):
    fall_detection: bool | None = None
    inactivity_hours: int | None = Field(None, ge=0, le=12)
    active_from: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    active_to: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")


def _care(dev: Device) -> dict:
    return {"kind": dev.kind, "fall_detection": dev.fall_detection is not False,
            "inactivity_hours": dev.inactivity_hours if dev.inactivity_hours is not None else 3,
            "active_from": dev.active_from or "08:00", "active_to": dev.active_to or "21:00",
            "last_active_at": as_utc(dev.last_active_at).isoformat() if dev.last_active_at else None}


@router.get("/devices/{device_id}/care")
def get_care(device_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _care(_get_member_device(db, user, device_id))


@router.put("/devices/{device_id}/care")
def set_care(device_id: str, body: CareIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Elderly care: fall detection on/off, 'no movement' alert after N hours within the day window."""
    dev = _get_member_device(db, user, device_id)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(dev, k, v)
    dev.inactivity_notified = False
    db.commit()
    return _care(dev)
