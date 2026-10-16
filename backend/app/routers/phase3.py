"""Phase 3: Emergency – School / Group, helpers, teacher contacts, plans."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (AbuseReport, Device, DeviceMember, FamilyInvite, DeviceSchool, School, HelpRequest, HelperResponse, LocationAccessLog, SosEvent, TeacherContact,
                      User)
from ..realtime import manager
from ..security import current_user, require_admin
from ..services import as_utc, device_users, distance_m, sos_info
from ..services_help import device_plan, ensure_sos, escalate_school, plan_allows, start_group
from .devices import _get_member_device
from .otp import normalize_phone
from ..places import alerted_keys as _alerted_keys

router = APIRouter(prefix="/api", tags=["phase3"])


# ---------------- Emergency buttons (family) ----------------
class EmergencyIn(BaseModel):
    target: str  # "school", "group" or "place" (the people at the current / given place: coach, tutor …)
    place_id: int | None = None


@router.post("/devices/{device_id}/emergency")
def emergency(device_id: str, body: EmergencyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    if body.target not in ("school", "group", "place"):
        raise HTTPException(400, "target must be school, group or place")
    if not plan_allows(db, dev, "school" if body.target == "place" else body.target):
        raise HTTPException(402, "Emergency – School and Emergency – Group are available on Smart and Guardian plans.")
    if body.target == "place":
        from .. import places
        from ..models import Geofence
        pid = body.place_id or (places.current_context(db, dev).get("place") or {}).get("id")
        g = db.get(Geofence, pid) if pid else None
        if g is None or g.device_pk != dev.id:
            raise HTTPException(400, "No place with people right now")
        if not places.people(db, g):
            raise HTTPException(400, f"No people added for {g.name} yet")
        sos = ensure_sos(db, dev, user)
        return {"sos_id": sos.id, "target": "place", **places.escalate_place(db, dev, sos, user, g)}
    sos = ensure_sos(db, dev, user)
    if body.target == "school":
        r = escalate_school(db, dev, sos, user)
        if r["staff"] == 0 and r["contacts"] == 0 and not r["already"]:
            return {"sos_id": sos.id, "target": "school", "warning": "No school or teacher contacts linked to this tracker.", **r}
        return {"sos_id": sos.id, "target": "school", **r}
    if not user.phone_verified:
        raise HTTPException(400, "Verify your mobile number first")
    r = start_group(db, dev, sos, user)
    db.commit()
    return {"sos_id": sos.id, "target": "group", **r}


@router.get("/sos/{sos_id}/status")
def sos_status(sos_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Family view: school escalation, group helpers (with distance), and who viewed the location."""
    sos = db.get(SosEvent, sos_id)
    if sos is None:
        raise HTTPException(404, "SOS not found")
    dev = _get_member_device(db, user, db.get(Device, sos.device_pk).device_id)
    hr = db.scalar(select(HelpRequest).where(HelpRequest.sos_id == sos.id).order_by(HelpRequest.created_at.desc()))
    helpers, notified = [], 0
    if hr:
        for resp, u in db.execute(select(HelperResponse, User).join(User, HelperResponse.user_id == User.id)
                                  .where(HelperResponse.help_id == hr.id)).all():
            notified += 1
            if resp.status == "accepted":
                d = (distance_m(dev.last_lat, dev.last_lon, u.helper_lat, u.helper_lon)
                     if dev.last_lat is not None and u.helper_lat is not None else None)
                helpers.append({"user_id": u.id, "name": u.name, "phone": u.phone, "distance_m": int(d) if d else None,
                                "lat": u.helper_lat, "lon": u.helper_lon, "accepted_at": as_utc(resp.accepted_at)})
    logs = db.execute(select(LocationAccessLog, User).outerjoin(User, LocationAccessLog.user_id == User.id)
                      .where(LocationAccessLog.sos_id == sos.id).order_by(LocationAccessLog.ts.desc()).limit(50)).all()
    return {
        "sos_id": sos.id, "status": sos.status, "source": sos.source, "plan": device_plan(db, dev),
        "school_notified_at": as_utc(sos.school_notified_at),
        "alerted_to": sorted(_alerted_keys(sos)),   # "school", "place:<id>"
        "group": None if hr is None else {"help_id": hr.id, "radius_m": hr.radius_m, "notified": notified,
                                          "accepted": len(helpers), "closed": hr.closed},
        "helpers": helpers,
        "access_log": [{"name": u.name if u else "link", "kind": l.kind, "ts": as_utc(l.ts)} for l, u in logs],
    }


# ---------------- Teacher contacts (manual, when school is not on SelfXTrack) ----------------
class ContactIn(BaseModel):
    name: str
    phone: str
    role: str = "teacher"


@router.get("/devices/{device_id}/teacher-contacts")
def list_contacts(device_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    return [{"id": c.id, "name": c.name, "phone": c.phone, "role": c.role, "place_id": c.place_id}
            for c in db.scalars(select(TeacherContact).where(TeacherContact.device_pk == dev.id)).all()]


def _my_devices(db: Session, user: User) -> list[Device]:
    return list(db.scalars(select(Device).join(DeviceMember, DeviceMember.device_pk == Device.id)
                           .where(DeviceMember.user_id == user.id)).all())


def _same_school(db: Session, user: User, dev: Device) -> list[Device]:
    """This child + my other children in the same school (school details are entered once, shared)."""
    if not dev.manual_school:
        return [dev]
    key = dev.manual_school.strip().lower()
    return [d for d in _my_devices(db, user) if d.id == dev.id or (d.manual_school or "").strip().lower() == key]


def _copy_contacts(db: Session, src: Device, dst: Device, user: User):
    have = {c.phone for c in db.scalars(select(TeacherContact).where(TeacherContact.device_pk == dst.id)).all()}
    for c in db.scalars(select(TeacherContact).where(TeacherContact.device_pk == src.id)).all():
        if c.phone not in have:
            db.add(TeacherContact(device_pk=dst.id, name=c.name, phone=c.phone, role=c.role, created_by=user.id))
            have.add(c.phone)


@router.get("/my-schools")
def my_schools(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Schools already set up for my children – pick one instead of typing it again."""
    out: dict[str, dict] = {}
    for d in _my_devices(db, user):
        if not d.manual_school:
            continue
        k = d.manual_school.strip().lower()
        e = out.setdefault(k, {"name": d.manual_school, "children": [], "contacts": []})
        e["children"].append(d.name or d.device_id)
        for c in db.scalars(select(TeacherContact).where(TeacherContact.device_pk == d.id)).all():
            if all(x["phone"] != c.phone for x in e["contacts"]):
                e["contacts"].append({"name": c.name, "phone": c.phone, "role": c.role})
    return list(out.values())


@router.post("/devices/{device_id}/teacher-contacts")
def add_contact(device_id: str, body: ContactIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    if len(db.scalars(select(TeacherContact).where(TeacherContact.device_pk == dev.id)).all()) >= 10:
        raise HTTPException(400, "Maximum 10 school contacts")
    phone = normalize_phone(body.phone)
    first = None
    for d in _same_school(db, user, dev):     # added once -> all my children in this school
        if db.scalar(select(TeacherContact).where(TeacherContact.device_pk == d.id, TeacherContact.phone == phone)):
            continue
        c = TeacherContact(device_pk=d.id, name=body.name.strip(), phone=phone, role=body.role, created_by=user.id)
        db.add(c)
        if d.id == dev.id:
            first = c
    db.commit()
    c = first or db.scalar(select(TeacherContact).where(TeacherContact.device_pk == dev.id, TeacherContact.phone == phone))
    return {"id": c.id, "name": c.name, "phone": c.phone, "role": c.role}


@router.delete("/devices/{device_id}/teacher-contacts/{cid}")
def delete_contact(device_id: str, cid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    c = db.get(TeacherContact, cid)
    if c and c.device_pk == dev.id:
        for d in _same_school(db, user, dev):
            for x in db.scalars(select(TeacherContact).where(TeacherContact.device_pk == d.id, TeacherContact.phone == c.phone)).all():
                db.delete(x)
        db.commit()
    return {"ok": True}


# ---------------- Helper side ----------------
class HelperLocIn(BaseModel):
    lat: float
    lon: float


class AvailabilityIn(BaseModel):
    available: bool


@router.post("/helpers/location")
def helper_location(body: HelperLocIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.helper_lat, user.helper_lon, user.helper_loc_at = body.lat, body.lon, datetime.now(timezone.utc)
    db.commit()
    # tell families whose emergency this helper accepted
    for resp, hr in db.execute(select(HelperResponse, HelpRequest).join(HelpRequest)
                               .where(HelperResponse.user_id == user.id, HelperResponse.status == "accepted",
                                      HelpRequest.closed.is_(False))).all():
        dev = db.get(Device, db.get(SosEvent, hr.sos_id).device_pk)
        manager.publish([u.id for u in device_users(db, dev)],
                        {"type": "helper_location", "sos_id": hr.sos_id, "user_id": user.id, "name": user.name,
                         "lat": body.lat, "lon": body.lon})
    return {"ok": True}


@router.put("/helpers/availability")
def availability(body: AvailabilityIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.helper_available = body.available
    db.commit()
    return {"available": user.helper_available}


def _help_for(db: Session, user: User, help_id: int) -> tuple[HelpRequest, HelperResponse, SosEvent, Device]:
    hr = db.get(HelpRequest, help_id)
    resp = db.scalar(select(HelperResponse).where(HelperResponse.help_id == help_id, HelperResponse.user_id == user.id))
    if hr is None or resp is None:
        raise HTTPException(404, "Help request not found")
    sos = db.get(SosEvent, hr.sos_id)
    return hr, resp, sos, db.get(Device, sos.device_pk)


@router.get("/help/{help_id}")
def help_detail(help_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    hr, resp, sos, dev = _help_for(db, user, help_id)
    if hr.closed or sos.status in ("resolved", "cancelled"):
        return {"help_id": help_id, "closed": True, "message": "The family has marked the child safe. Thank you."}
    d = None
    if dev.last_lat is not None and user.helper_lat is not None:
        d = distance_m(dev.last_lat, dev.last_lon, user.helper_lat, user.helper_lon)
    base = {"help_id": help_id, "closed": False, "status": resp.status,
            "distance_m": int(round(d / 100.0) * 100) if d is not None else None}
    if resp.status != "accepted":
        return base   # Level 1: approximate distance only
    db.add(LocationAccessLog(sos_id=sos.id, user_id=user.id, kind="helper"))
    db.commit()
    family = [{"name": u.name, "phone": u.phone} for u in device_users(db, dev)]
    info = sos_info(dev, sos)
    info.pop("device_id", None)
    return {**base, **info, "family": family,
            "safety": "Your safety first. Do not confront anyone. Observe, call 112, and guide the family/police."}


@router.post("/help/{help_id}/accept")
def help_accept(help_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    hr, resp, sos, dev = _help_for(db, user, help_id)
    if hr.closed:
        raise HTTPException(410, "This emergency has ended")
    if resp.status != "accepted":
        resp.status, resp.accepted_at = "accepted", datetime.now(timezone.utc)
        db.commit()
        from .. import notify
        users = device_users(db, dev)
        notify.push(users, "🙋 Helper is coming", f"{user.name} is going to help.",
                    {"type": "helper_accepted", "sos_id": sos.id, "name": user.name})
        manager.publish([u.id for u in users], {"type": "helper_accepted", "sos_id": sos.id, "name": user.name})
    return help_detail(help_id, user, db)


@router.post("/help/{help_id}/decline")
def help_decline(help_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    hr, resp, sos, dev = _help_for(db, user, help_id)
    if resp.status == "notified":
        resp.status = "declined"
        db.commit()
    return {"ok": True}


class ReportIn(BaseModel):
    user_id: int
    sos_id: int | None = None
    reason: str = Field(min_length=3, max_length=500)


@router.post("/reports")
def report(body: ReportIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.add(AbuseReport(reporter_id=user.id, reported_user_id=body.user_id, sos_id=body.sos_id, reason=body.reason))
    # auto-suspend after 3 reports from different users
    reporters = {r.reporter_id for r in db.scalars(select(AbuseReport).where(AbuseReport.reported_user_id == body.user_id)).all()}
    reporters.add(user.id)
    if len(reporters) >= 3:
        u = db.get(User, body.user_id)
        if u:
            u.banned = True
    db.commit()
    return {"ok": True}


# ---------------- Plans ----------------
class PlanIn(BaseModel):
    email: str
    plan: str


@router.post("/admin/users/plan", dependencies=[Depends(require_admin)])
def set_plan(body: PlanIn, db: Session = Depends(get_db)):
    """Testing / support: set a user's plan (Phase 4 replaces this with Razorpay subscriptions)."""
    if body.plan not in ("basic", "smart", "guardian"):
        raise HTTPException(400, "plan must be basic, smart or guardian")
    u = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if u is None:
        raise HTTPException(404, "User not found")
    u.plan = body.plan
    db.commit()
    return {"email": u.email, "plan": u.plan}


# ---------------- Child setup (one-time, per tracker) ----------------
class ProfileIn(BaseModel):
    name: str | None = None
    kind: str | None = None
    manual_school: str | None = None
    manual_class: str | None = None
    public_holidays: bool | None = None


def _setup(db: Session, dev: Device) -> dict:
    links = db.execute(select(DeviceSchool, School).join(School, School.id == DeviceSchool.school_id)
                       .where(DeviceSchool.device_pk == dev.id)).all()
    family = db.execute(select(User, DeviceMember).join(DeviceMember, DeviceMember.user_id == User.id)
                        .where(DeviceMember.device_pk == dev.id)).all()
    return {
        "device_id": dev.device_id, "name": dev.name, "kind": dev.kind,
        "schools": [{"id": s.id, "name": s.name, "class_name": l.class_name} for l, s in links],
        "manual_school": dev.manual_school, "manual_class": dev.manual_class,
        "contacts": db.query(TeacherContact).filter(TeacherContact.device_pk == dev.id).count(),
        "public_holidays": dev.public_holidays if dev.public_holidays is not None else True,
        "family": [{"name": u.name, "email": u.email, "phone": u.phone, "role": m.role} for u, m in family],
        "invites": [_invite_out(db, i) for i in db.scalars(select(FamilyInvite).where(
            FamilyInvite.device_pk == dev.id, FamilyInvite.status == "pending")).all()],
    }


def _invite_out(db: Session, i: FamilyInvite) -> dict:
    u = db.scalar(select(User).where(User.phone == i.phone, User.phone_verified.is_(True)))
    return {"id": i.id, "name": i.name, "phone": i.phone, "ready": u is not None, "relation": i.relation or "family"}


class RoleIn(BaseModel):
    relation: str   # parent / family


@router.put("/devices/{device_id}/family/{member_phone}/role")
def set_family_role(device_id: str, member_phone: str, body: RoleIn, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    """Parent = gets the SOS alarm immediately with the owner; Family = after 2 min if parents don't respond.
    Applies to all my children."""
    _get_member_device(db, user, device_id)
    member = db.scalar(select(User).where(User.phone == normalize_phone(member_phone)))
    if member is None:
        raise HTTPException(404, "Member not found")
    role = "parent" if body.relation == "parent" else "family"
    for d in _owned_devices(db, user):
        for m in d.members:
            if m.user_id == member.id and m.role != "owner":
                m.role = role
    db.commit()
    return _setup(db, _get_member_device(db, user, device_id))


class InviteIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    phone: str
    relation: str = "family"        # parent = rings immediately on SOS · family = after 2 min


@router.post("/devices/{device_id}/family-invites")
def invite_family(device_id: str, body: InviteIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    phone = normalize_phone(body.phone)
    for d in _owned_devices(db, user) or [dev]:   # family is shared by all my children
        if db.scalar(select(FamilyInvite).where(FamilyInvite.device_pk == d.id, FamilyInvite.phone == phone,
                                                FamilyInvite.status == "pending")) is None:
            db.add(FamilyInvite(device_pk=d.id, name=body.name.strip(), phone=phone, invited_by=user.id,
                                relation="parent" if body.relation == "parent" else "family"))
    db.commit()
    return _setup(db, dev)


def _owned_devices(db: Session, user: User) -> list[Device]:
    return list(db.scalars(select(Device).join(DeviceMember, DeviceMember.device_pk == Device.id)
                           .where(DeviceMember.user_id == user.id, DeviceMember.role == "owner")).all())


@router.post("/devices/{device_id}/family-invites/{iid}/accept")
def accept_family(device_id: str, iid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    inv = db.get(FamilyInvite, iid)
    if inv is None or inv.device_pk != dev.id or inv.status != "pending":
        raise HTTPException(404, "Request not found")
    member = db.scalar(select(User).where(User.phone == inv.phone, User.phone_verified.is_(True)))
    if member is None:
        raise HTTPException(400, f"{inv.name} has not registered with {inv.phone} yet")
    from ..plans import PLANS
    limit = PLANS[device_plan(db, dev)]["family"]
    if sum(1 for m in dev.members if m.role != "owner") >= limit:
        raise HTTPException(402, f"Your plan allows {limit} family members. Upgrade to add more.")
    for i in db.scalars(select(FamilyInvite).where(FamilyInvite.phone == inv.phone, FamilyInvite.status == "pending")).all():
        d = db.get(Device, i.device_pk)
        if not any(m.user_id == user.id for m in d.members):
            continue                                   # only my children
        if not any(m.user_id == member.id for m in d.members):
            db.add(DeviceMember(device_pk=d.id, user_id=member.id, role=i.relation or "family"))
        i.status = "accepted"
    db.commit()
    db.refresh(dev)
    from .. import notify
    notify.push([member], "👪 You were added", f"You can now see {dev.name or dev.device_id}'s location and SOS alerts.",
                {"type": "family_added", "device_id": dev.device_id})
    manager.publish([member.id], {"type": "family_added", "device_id": dev.device_id})
    return _setup(db, dev)


@router.delete("/devices/{device_id}/family-invites/{iid}")
def cancel_family(device_id: str, iid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    inv = db.get(FamilyInvite, iid)
    if inv and inv.device_pk == dev.id:
        for d in _owned_devices(db, user) or [dev]:
            for i in db.scalars(select(FamilyInvite).where(FamilyInvite.device_pk == d.id, FamilyInvite.phone == inv.phone,
                                                           FamilyInvite.status == "pending")).all():
                db.delete(i)
        db.commit()
    return _setup(db, dev)


@router.delete("/devices/{device_id}/family/{member_phone}")
def remove_family(device_id: str, member_phone: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Remove a family member from ALL my children."""
    _get_member_device(db, user, device_id)
    phone = normalize_phone(member_phone)
    member = db.scalar(select(User).where(User.phone == phone))
    if member is None or member.id == user.id:
        raise HTTPException(400, "Cannot remove")
    for d in _owned_devices(db, user):
        for m in list(d.members):
            if m.user_id == member.id and m.role != "owner":
                db.delete(m)
    db.commit()
    return _setup(db, _get_member_device(db, user, device_id))


@router.get("/devices/{device_id}/setup")
def get_setup(device_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    _sync_family(db, user, dev)
    return _setup(db, dev)


def _sync_family(db: Session, user: User, dev: Device):
    """Family is shared: give this child every family member + pending request from my other children."""
    owned = _owned_devices(db, user)
    if dev.id not in {d.id for d in owned}:
        return
    have_users = {m.user_id for m in dev.members}
    have_inv = {i.phone for i in db.scalars(select(FamilyInvite).where(FamilyInvite.device_pk == dev.id,
                                                                       FamilyInvite.status == "pending")).all()}
    for d in owned:
        if d.id == dev.id:
            continue
        for m in d.members:
            if m.role in ("family", "parent") and m.user_id not in have_users:
                db.add(DeviceMember(device_pk=dev.id, user_id=m.user_id, role=m.role))
                have_users.add(m.user_id)
        for i in db.scalars(select(FamilyInvite).where(FamilyInvite.device_pk == d.id, FamilyInvite.status == "pending")).all():
            if i.phone not in have_inv:
                db.add(FamilyInvite(device_pk=dev.id, name=i.name, phone=i.phone, invited_by=i.invited_by,
                                    relation=i.relation))
                have_inv.add(i.phone)
    db.commit()
    db.refresh(dev)


@router.put("/devices/{device_id}/setup")
def put_setup(device_id: str, body: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    if body.name is not None: dev.name = body.name.strip() or dev.name
    if body.kind is not None: dev.kind = body.kind
    if body.manual_school is not None:
        dev.manual_school = body.manual_school.strip() or None
        sib = [d for d in _same_school(db, user, dev) if d.id != dev.id]
        if sib:                                   # same school as another child -> reuse its staff list
            _copy_contacts(db, sib[0], dev, user)
    if body.manual_class is not None: dev.manual_class = body.manual_class.strip() or None
    if body.public_holidays is not None: dev.public_holidays = body.public_holidays
    db.commit()
    return _setup(db, dev)


# ---------------- School dashboard for teachers / staff (no codes) ----------------
# A parent adds a teacher's mobile number in Child setup. When that teacher uses the SelfXTrack app
# with the same (OTP-verified) number, the child appears on their School dashboard automatically.
def _staff_devices(db: Session, user: User) -> list[tuple[Device, list[TeacherContact]]]:
    """Children where my verified number was added as a teacher / coach / tutor – one row per child,
    with all my contact entries for that child (I may be listed at more than one place)."""
    if not user.phone_verified or not user.phone:
        return []
    rows = db.execute(select(Device, TeacherContact).join(TeacherContact, TeacherContact.device_pk == Device.id)
                      .where(TeacherContact.phone == user.phone).order_by(Device.id, TeacherContact.id)).all()
    out: dict[int, tuple[Device, list[TeacherContact]]] = {}
    for d, c in rows:
        out.setdefault(d.id, (d, []))[1].append(c)
    return list(out.values())


def _visible_sos(db: Session, dev: Device, contacts: list[TeacherContact], active_only: bool = True):
    """Latest SOS of this child that was sent to one of my places (school / my coaching place …)."""
    from ..places import can_see
    q = select(SosEvent).where(SosEvent.device_pk == dev.id, SosEvent.school_alerted.is_(True))
    if active_only:
        q = q.where(SosEvent.status.in_(["active", "acknowledged"]))
    return [ev for ev in db.scalars(q.order_by(SosEvent.id.desc())).all() if any(can_see(db, ev, c) for c in contacts)]


def _place_info(db: Session, dev: Device, contacts: list[TeacherContact]) -> tuple[str | None, str]:
    """(place name, place kind) where I am responsible for this child – school, swimming, tuition …"""
    from ..models import Geofence
    for c in contacts:
        g = db.get(Geofence, c.place_id) if c.place_id else None
        if g is not None:
            return g.name, g.kind or "other"
    return dev.manual_school, "school"


def _place_label(db: Session, dev: Device, contacts: list[TeacherContact]) -> str | None:
    return _place_info(db, dev, contacts)[0]


@router.get("/staff/board")
def staff_board(user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..models import HelpRequest
    if not user.phone_verified:
        return {"verified": False, "children": []}
    out = []
    for dev, cs in _staff_devices(db, user):
        # only an SOS sent to MY place (Emergency – School / – place, or no family response) – never a buzzer alone
        evs = _visible_sos(db, dev, cs)
        ev = evs[0] if evs else None
        place, place_kind = _place_info(db, dev, cs)
        row = {"device_id": dev.device_id, "name": dev.name or dev.device_id, "school": place, "place_kind": place_kind,
               "kind": dev.kind or "child", "class_name": dev.manual_class if place_kind == "school" else None,
               "my_role": cs[0].role, "sos": None, "parents": []}
        if ev is not None:   # location only while an SOS is active
            db.add(LocationAccessLog(sos_id=ev.id, user_id=user.id, kind="school"))
            plan = device_plan(db, dev)
            group = db.scalar(select(HelpRequest).where(HelpRequest.sos_id == ev.id, HelpRequest.closed.is_(False)))
            # contacts only during an SOS: the parent who raised it first, then other family
            raiser = ev.escalated_by or (ev.acknowledged_by if ev.source == "parent" else None)
            fam = [m for m in dev.members if m.user.phone_verified and m.user.phone]
            fam.sort(key=lambda m: (m.user_id != raiser, m.role != "owner"))
            row["parents"] = [{"name": m.user.name, "phone": m.user.phone, "role": m.role,
                               "raised": m.user_id == raiser} for m in fam]
            row["sos"] = {**sos_info(dev, ev), "status": ev.status, "source": ev.source,
                          "school_alerted": ev.school_notified_at is not None, "plan": plan,
                          "group_allowed": plan == "guardian", "group_started": group is not None}
        out.append(row)
    db.commit()
    out.sort(key=lambda r: (r["sos"] is None, r["school"] or "", r["name"]))
    return {"verified": True, "children": out}


def _staff_sos(db: Session, user: User, sos_id: int) -> tuple[Device, SosEvent]:
    ev = db.get(SosEvent, sos_id)
    if ev is None or ev.status not in ("active", "acknowledged") or not ev.school_alerted:
        raise HTTPException(404, "SOS not active")
    dev = db.get(Device, ev.device_pk)
    mine = {d.id: cs for d, cs in _staff_devices(db, user)}
    if dev.id not in mine:
        raise HTTPException(403, "This child is not on your school dashboard")
    from ..places import can_see
    if not any(can_see(db, ev, c) for c in mine[dev.id]):
        raise HTTPException(404, "SOS not active")
    return dev, ev


@router.post("/staff/sos/{sos_id}/acknowledge")
def staff_ack(sos_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev, ev = _staff_sos(db, user, sos_id)
    if ev.status == "active":
        ev.status, ev.acknowledged_by = "acknowledged", user.id
    db.commit()
    from .. import notify
    notify.push(device_users(db, dev), "🏫 School is responding", f"{user.name} (school) is on it.",
                {"type": "sos_update", "sos_id": ev.id, "device_id": dev.device_id})
    manager.publish([u.id for u in device_users(db, dev)], {"type": "sos_update", "sos_id": ev.id, "device_id": dev.device_id})
    return {"ok": True}


@router.post("/staff/sos/{sos_id}/group")
def staff_group(sos_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Removed: only the parent (Smart / Guardian plan) can start Emergency – Group."""
    raise HTTPException(403, "Only the child's parent can start Emergency – Group.")
    dev, ev = _staff_sos(db, user, sos_id)
    if device_plan(db, dev) != "guardian":
        raise HTTPException(402, "Emergency – Group from school is available on the premium (Guardian) plan.")
    r = start_group(db, dev, ev, user)
    db.commit()
    from .. import notify
    notify.push(device_users(db, dev), "👥 School requested group help",
                f"{user.name} (school) asked nearby SelfXTrack users to help.",
                {"type": "group_started", "sos_id": ev.id, "device_id": dev.device_id})
    return {"sos_id": ev.id, **r}


@router.get("/staff/sos/{sos_id}/track")
def staff_track(sos_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Live tracking for school staff – ONLY while the SOS is active. Last 30 min trail + current position."""
    from datetime import timedelta
    from ..models import Location
    dev, ev = _staff_sos(db, user, sos_id)
    since = max(as_utc(ev.started_at) - timedelta(minutes=10), datetime.now(timezone.utc) - timedelta(minutes=30))
    pts = db.scalars(select(Location).where(Location.device_pk == dev.id, Location.ts >= since).order_by(Location.ts)).all()
    db.add(LocationAccessLog(sos_id=ev.id, user_id=user.id, kind="school"))
    db.commit()
    return {**sos_info(dev, ev), "status": ev.status, "trail": [{"lat": p.lat, "lon": p.lon} for p in pts]}


@router.get("/staff/history")
def staff_history(days: int = 30, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """School dashboard: past SOS events of my students (last 30 days) – no locations, only timeline facts."""
    from datetime import timedelta as _td
    since = datetime.now(timezone.utc) - _td(days=min(days, 30))
    out = []
    for dev, cs in _staff_devices(db, user):
        for ev in [e for e in _visible_sos(db, dev, cs, active_only=False) if as_utc(e.started_at) >= since]:
            resp = db.get(User, ev.acknowledged_by) if ev.acknowledged_by else None
            out.append({"sos_id": ev.id, "name": dev.name or dev.device_id, "class_name": dev.manual_class,
                        "school": _place_label(db, dev, cs), "started_at": as_utc(ev.started_at).isoformat(),
                        "status": ev.status, "source": ev.source, "responder": resp.name if resp else None,
                        "resolved_at": as_utc(ev.resolved_at).isoformat() if ev.resolved_at else None,
                        "school_alerted": ev.school_notified_at is not None})
    out.sort(key=lambda x: x["started_at"], reverse=True)
    return out
