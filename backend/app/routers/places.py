"""Places (any number: home, school, tuition, swimming, grandma's …) with time slots + people, and Transport
(bus, van, auto, cab) with optional beacon + driver. Used by Child setup in the app.

The older /geofences, /teacher-contacts and /buses endpoints keep working for older app versions.
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import places as P
from ..db import get_db
from ..models import Bus, Device, DeviceBus, DeviceMember, Geofence, TeacherContact, Transport, User
from ..security import current_user
from .devices import _get_member_device
from .otp import normalize_phone

router = APIRouter(prefix="/api", tags=["places"])


# ---------------------------------------------------------------- schemas
class Slot(BaseModel):
    days: list[int]
    start: str
    end: str


class PlaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: str = "other"
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    radius_m: int = Field(150, ge=30, le=2000)
    note: str | None = Field(None, max_length=120)
    schedule: list[Slot] = []
    alert_late: bool = True
    notify_enter: bool = True
    notify_exit: bool = True


class PersonIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    phone: str = Field(min_length=10, max_length=20)
    role: str = "other"


class TransportIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: str = "bus"
    beacon_id: str | None = Field(None, max_length=64)
    driver_name: str | None = Field(None, max_length=80)
    driver_phone: str | None = Field(None, max_length=20)
    place_ids: list[int] = []
    all_children: bool = False


# ---------------------------------------------------------------- helpers
def _place(db: Session, dev: Device, pid: int) -> Geofence:
    g = db.get(Geofence, pid)
    if g is None or g.device_pk != dev.id:
        raise HTTPException(404, "Place not found")
    return g


def _place_out(db: Session, dev: Device, g: Geofence) -> dict:
    return {"id": g.id, "name": g.name, "kind": g.kind or "other", "lat": g.lat, "lon": g.lon, "radius_m": g.radius_m,
            "note": g.note, "schedule": P.parse_schedule(g.schedule) if g.schedule else [],
            "alert_late": g.alert_late is not False, "notify_enter": g.notify_enter, "notify_exit": g.notify_exit,
            "inside": P.is_at(dev, g) if dev.last_lat is not None else None,
            "people": [{"id": c.id, "name": c.name, "phone": c.phone, "role": c.role} for c in P.people(db, g)]}


def _validate(body: PlaceIn) -> list[dict]:
    if body.kind not in P.KINDS:
        raise HTTPException(400, "Unknown place type")
    try:
        return P.parse_schedule([s.model_dump() for s in body.schedule])
    except ValueError as e:
        raise HTTPException(400, str(e))


def _apply(dev: Device, g: Geofence, body: PlaceIn, slots: list[dict]):
    g.name, g.kind, g.lat, g.lon, g.radius_m = body.name.strip(), body.kind, body.lat, body.lon, body.radius_m
    g.note = (body.note or "").strip() or None
    g.schedule = json.dumps(slots) if slots else None
    g.alert_late, g.notify_enter, g.notify_exit = body.alert_late, body.notify_enter, body.notify_exit
    if g.kind == "school":                     # school name / class are shown to school staff + used for siblings
        dev.manual_school = g.name
        if g.note:
            dev.manual_class = g.note


def _adopt_school_contacts(db: Session, dev: Device):
    """Older school contacts without a place join the child's school place once there is exactly one."""
    schools = db.scalars(select(Geofence).where(Geofence.device_pk == dev.id, Geofence.kind == "school")).all()
    if len(schools) == 1:
        for c in db.scalars(select(TeacherContact).where(TeacherContact.device_pk == dev.id,
                                                         TeacherContact.place_id.is_(None))).all():
            c.place_id = schools[0].id


def _owned(db: Session, user: User) -> list[Device]:
    return list(db.scalars(select(Device).join(DeviceMember, DeviceMember.device_pk == Device.id)
                           .where(DeviceMember.user_id == user.id, DeviceMember.role == "owner")).all())


# ---------------------------------------------------------------- places
@router.get("/devices/{device_id}/places")
def list_places(device_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    rows = db.scalars(select(Geofence).where(Geofence.device_pk == dev.id).order_by(Geofence.id)).all()
    order = {k: i for i, k in enumerate(P.KINDS)}
    return sorted((_place_out(db, dev, g) for g in rows), key=lambda x: (order.get(x["kind"], 9), x["name"].lower()))


@router.post("/devices/{device_id}/places")
def add_place(device_id: str, body: PlaceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    if len(db.scalars(select(Geofence.id).where(Geofence.device_pk == dev.id)).all()) >= P.MAX_PLACES:
        raise HTTPException(400, f"Maximum {P.MAX_PLACES} places per tracker")
    slots = _validate(body)
    g = Geofence(device_pk=dev.id, name=body.name.strip(), lat=body.lat, lon=body.lon)
    _apply(dev, g, body, slots)
    db.add(g)
    db.flush()
    _adopt_school_contacts(db, dev)
    db.commit()
    return _place_out(db, dev, g)


@router.put("/devices/{device_id}/places/{pid}")
def edit_place(device_id: str, pid: int, body: PlaceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    g = _place(db, dev, pid)
    moved = abs(g.lat - body.lat) > 1e-6 or abs(g.lon - body.lon) > 1e-6 or g.radius_m != body.radius_m
    _apply(dev, g, body, _validate(body))
    if moved:
        g.inside = None                        # re-learn inside/outside silently at the next report
    _adopt_school_contacts(db, dev)
    db.commit()
    return _place_out(db, dev, g)


@router.delete("/devices/{device_id}/places/{pid}")
def delete_place(device_id: str, pid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    g = _place(db, dev, pid)
    for c in P.people(db, g):
        db.delete(c)
    for t in db.scalars(select(Transport).where(Transport.device_pk == dev.id)).all():
        ids = [i for i in json.loads(t.place_ids or "[]") if i != g.id]
        t.place_ids = json.dumps(ids)
    db.delete(g)
    db.commit()
    return {"ok": True}


@router.post("/devices/{device_id}/places/{pid}/people")
def add_person(device_id: str, pid: int, body: PersonIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    g = _place(db, dev, pid)
    if body.role not in P.ROLES:
        raise HTTPException(400, "Unknown role")
    if len(P.people(db, g)) >= 10:
        raise HTTPException(400, "Maximum 10 people per place")
    phone = normalize_phone(body.phone)
    targets = [(dev, g)]
    if g.kind == "school":                     # same school as my other children -> add once, shared
        for d in _owned(db, user):
            if d.id == dev.id:
                continue
            sib = db.scalar(select(Geofence).where(Geofence.device_pk == d.id, Geofence.kind == "school",
                                                   Geofence.name.ilike(g.name)))
            if sib:
                targets.append((d, sib))
    for d, place in targets:
        if not db.scalar(select(TeacherContact).where(TeacherContact.place_id == place.id, TeacherContact.phone == phone)):
            db.add(TeacherContact(device_pk=d.id, place_id=place.id, name=body.name.strip(), phone=phone,
                                  role=body.role, created_by=user.id))
    db.commit()
    return _place_out(db, dev, g)


@router.delete("/devices/{device_id}/places/{pid}/people/{cid}")
def remove_person(device_id: str, pid: int, cid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    g = _place(db, dev, pid)
    c = db.get(TeacherContact, cid)
    if c is None or c.place_id != g.id:
        raise HTTPException(404, "Person not found")
    db.delete(c)
    db.commit()
    return _place_out(db, dev, g)


@router.get("/devices/{device_id}/now")
def now(device_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Where the child should be right now (from the place schedules) and who is responsible there."""
    dev = _get_member_device(db, user, device_id)
    from ..ai import hhmm, live_trip, route_paused
    paused = route_paused(dev)
    trip = live_trip(db, dev, user.lang or "en")     # None when the child is not travelling right now
    return {**P.current_context(db, dev), "today": P.schedule_today(db, dev),
            "route_paused_until": hhmm(dev.route_ok_until) if paused else None,
            "route_paused_trip": bool(paused and dev.route_ok_trip),
            "trip": {k: trip.get(k) for k in ("started_at", "started_from", "heading_to", "eta_time")} if trip else None}


# ---------------------------------------------------------------- transport
def _transport_out(db: Session, dev: Device, t: Transport) -> dict:
    bus = db.get(Bus, t.bus_id) if t.bus_id else None
    return {"id": t.id, "name": t.name, "kind": t.kind, "beacon_id": bus.beacon_id if bus else None,
            "driver_name": t.driver_name, "driver_phone": t.driver_phone,
            "place_ids": json.loads(t.place_ids or "[]"), "on_now": bool(bus and dev.on_bus_id == bus.id)}


def _link_beacon(db: Session, d: Device, beacon: str | None, name: str, user: User) -> int | None:
    if not beacon:
        return None
    bid = beacon.strip().upper()
    bus = db.scalar(select(Bus).where(Bus.beacon_id == bid))
    if bus is None:
        bus = Bus(name=name, beacon_id=bid, created_by=user.id)
        db.add(bus)
        db.flush()
    if db.scalar(select(DeviceBus).where(DeviceBus.device_pk == d.id, DeviceBus.bus_id == bus.id)) is None:
        db.add(DeviceBus(device_pk=d.id, bus_id=bus.id))
    return bus.id


def _unlink_beacon(db: Session, d: Device, bus_id: int | None, keep: int | None = None):
    """Remove the beacon link when no other transport of this child uses that bus."""
    if not bus_id:
        return
    others = db.scalars(select(Transport).where(Transport.device_pk == d.id, Transport.bus_id == bus_id,
                                                Transport.id != (keep or -1))).all()
    if not others:
        link = db.scalar(select(DeviceBus).where(DeviceBus.device_pk == d.id, DeviceBus.bus_id == bus_id))
        if link:
            db.delete(link)
        if d.on_bus_id == bus_id:
            d.on_bus_id = None


def _check_transport(db: Session, dev: Device, body: TransportIn) -> list[int]:
    if body.kind not in P.TRANSPORT_KINDS:
        raise HTTPException(400, "Unknown transport type")
    if body.beacon_id and len(body.beacon_id.strip()) < 3:
        raise HTTPException(400, "Beacon ID is too short")
    mine = {g.id for g in db.scalars(select(Geofence).where(Geofence.device_pk == dev.id)).all()}
    return [i for i in dict.fromkeys(body.place_ids) if i in mine]


@router.get("/devices/{device_id}/transports")
def list_transports(device_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    return [_transport_out(db, dev, t) for t in
            db.scalars(select(Transport).where(Transport.device_pk == dev.id).order_by(Transport.id)).all()]


@router.post("/devices/{device_id}/transports")
def add_transport(device_id: str, body: TransportIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    ids = _check_transport(db, dev, body)
    phone = normalize_phone(body.driver_phone) if body.driver_phone else None
    targets = [dev] + ([d for d in _owned(db, user) if d.id != dev.id] if body.all_children else [])
    for d in targets:
        if len(db.scalars(select(Transport.id).where(Transport.device_pk == d.id)).all()) >= 10:
            if d.id == dev.id:
                raise HTTPException(400, "Maximum 10 transports per tracker")
            continue
        db.add(Transport(device_pk=d.id, name=body.name.strip(), kind=body.kind, created_by=user.id,
                         bus_id=_link_beacon(db, d, body.beacon_id, body.name.strip(), user),
                         driver_name=(body.driver_name or "").strip() or None, driver_phone=phone,
                         place_ids=json.dumps(ids if d.id == dev.id else [])))
    db.commit()
    return list_transports(device_id, user, db)


@router.put("/devices/{device_id}/transports/{tid}")
def edit_transport(device_id: str, tid: int, body: TransportIn, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    t = db.get(Transport, tid)
    if t is None or t.device_pk != dev.id:
        raise HTTPException(404, "Transport not found")
    ids = _check_transport(db, dev, body)
    old_bus = t.bus_id
    t.bus_id = _link_beacon(db, dev, body.beacon_id, body.name.strip(), user)
    if old_bus and old_bus != t.bus_id:
        _unlink_beacon(db, dev, old_bus, keep=t.id)
    t.name, t.kind = body.name.strip(), body.kind
    t.driver_name = (body.driver_name or "").strip() or None
    t.driver_phone = normalize_phone(body.driver_phone) if body.driver_phone else None
    t.place_ids = json.dumps(ids)
    db.commit()
    return list_transports(device_id, user, db)


@router.delete("/devices/{device_id}/transports/{tid}")
def delete_transport(device_id: str, tid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    t = db.get(Transport, tid)
    if t is None or t.device_pk != dev.id:
        raise HTTPException(404, "Transport not found")
    bus = t.bus_id
    db.delete(t)
    db.flush()
    _unlink_beacon(db, dev, bus)
    db.commit()
    return list_transports(device_id, user, db)
