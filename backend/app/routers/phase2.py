"""Phase 2: safe zones, live share links, school safety circle."""
import json
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Device, DeviceSchool, Geofence, Location, LocationAccessLog, School, SchoolStaff, ShareLink, SosEvent, User
from ..security import current_user
from ..services import active_sos, as_utc, is_online, sos_info
from .devices import _get_member_device

router = APIRouter(prefix="/api", tags=["phase2"])
public = APIRouter(tags=["public"])


# ---------------- Safe zones ----------------
class GeofenceIn(BaseModel):
    name: str
    lat: float
    lon: float
    radius_m: int = Field(150, ge=50, le=5000)
    notify_enter: bool = True
    notify_exit: bool = True


class GeofenceOut(GeofenceIn):
    id: int
    inside: bool | None


@router.get("/devices/{device_id}/geofences", response_model=list[GeofenceOut])
def list_geofences(device_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    return [GeofenceOut(id=g.id, name=g.name, lat=g.lat, lon=g.lon, radius_m=g.radius_m, notify_enter=g.notify_enter,
                        notify_exit=g.notify_exit, inside=g.inside)
            for g in db.scalars(select(Geofence).where(Geofence.device_pk == dev.id)).all()]


@router.post("/devices/{device_id}/geofences", response_model=GeofenceOut)
def add_geofence(device_id: str, body: GeofenceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    from ..places import MAX_PLACES, kind_from_name
    if len(db.scalars(select(Geofence).where(Geofence.device_pk == dev.id)).all()) >= MAX_PLACES:
        raise HTTPException(400, f"Maximum {MAX_PLACES} places per tracker")
    g = Geofence(device_pk=dev.id, kind=kind_from_name(body.name), **body.model_dump())
    db.add(g)
    db.commit()
    return GeofenceOut(id=g.id, inside=g.inside, **body.model_dump())


@router.delete("/devices/{device_id}/geofences/{gid}")
def delete_geofence(device_id: str, gid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    g = db.get(Geofence, gid)
    if g is None or g.device_pk != dev.id:
        raise HTTPException(404, "Safe zone not found")
    from ..models import TeacherContact
    for c in db.scalars(select(TeacherContact).where(TeacherContact.place_id == g.id)).all():
        db.delete(c)
    db.delete(g)
    db.commit()
    return {"ok": True}


# ---------------- Live share links ----------------
class ShareLinkIn(BaseModel):
    minutes: int = Field(60, ge=5, le=24 * 60)
    for_sos: bool = False


class ShareLinkOut(BaseModel):
    token: str
    url: str
    expires_at: datetime
    active: bool


def _link_active(l: ShareLink) -> bool:
    return not l.revoked and as_utc(l.expires_at) > datetime.now(timezone.utc)


def _link_out(l: ShareLink) -> ShareLinkOut:
    return ShareLinkOut(token=l.token, url=f"{settings.public_base_url.rstrip('/')}/live/{l.token}",
                        expires_at=as_utc(l.expires_at), active=_link_active(l))


@router.post("/devices/{device_id}/share-links", response_model=ShareLinkOut)
def create_link(device_id: str, body: ShareLinkIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    sos = active_sos(db, dev) if body.for_sos else None
    l = ShareLink(device_pk=dev.id, token=secrets.token_urlsafe(16), created_by=user.id,
                  expires_at=datetime.now(timezone.utc) + timedelta(minutes=body.minutes),
                  sos_id=sos.id if sos else None)
    db.add(l)
    db.commit()
    return _link_out(l)


@router.get("/devices/{device_id}/share-links", response_model=list[ShareLinkOut])
def list_links(device_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    links = db.scalars(select(ShareLink).where(ShareLink.device_pk == dev.id).order_by(ShareLink.created_at.desc())
                       .limit(20)).all()
    return [_link_out(l) for l in links if _link_active(l)]


@router.post("/share-links/{token}/stop")
def stop_link(token: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    l = db.scalar(select(ShareLink).where(ShareLink.token == token))
    if l is None:
        raise HTTPException(404, "Link not found")
    _get_member_device(db, user, db.get(Device, l.device_pk).device_id)
    l.revoked = True
    db.commit()
    return {"ok": True}


@public.get("/api/live/{token}")
def live_data(token: str, db: Session = Depends(get_db)):
    """Public, read-only, time-limited. Returns only this device's latest position + last 30 min trail."""
    l = db.scalar(select(ShareLink).where(ShareLink.token == token))
    if l is None or not _link_active(l):
        raise HTTPException(410, "This live link has expired or was stopped by the family.")
    dev = db.get(Device, l.device_pk)
    since = datetime.now(timezone.utc) - timedelta(minutes=30)
    trail = db.scalars(select(Location).where(Location.device_pk == dev.id, Location.ts >= since)
                       .order_by(Location.ts.asc()).limit(500)).all()
    sos = active_sos(db, dev)
    info = sos_info(dev, sos)
    info.pop("device_id", None)
    return {**info, "sos_active": sos is not None, "online": is_online(dev),
            "expires_at": as_utc(l.expires_at).isoformat(),
            "trail": [[p.lat, p.lon] for p in trail]}


_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{16,64}")
# Content-Security-Policy for the public page: only our API, the pinned Leaflet files and OSM map tiles.
_LIVE_CSP = ("default-src 'none'; script-src 'self' 'unsafe-inline' https://unpkg.com; "
             "style-src 'unsafe-inline' https://unpkg.com; img-src data: https://unpkg.com https://*.tile.openstreetmap.org; "
             "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


@public.get("/live/{token}", response_class=HTMLResponse)
def live_page(token: str):
    # token goes into a script -> accept only the characters our tokens use, and embed it JSON-encoded
    if not _TOKEN_RE.fullmatch(token):
        raise HTTPException(404, "Link not found")
    return HTMLResponse(LIVE_HTML.replace("__TOKEN_JSON__", json.dumps(token)), headers={"Content-Security-Policy": _LIVE_CSP})


LIVE_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SelfXTrack live location</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
 integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin=""/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
 integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<style>body{margin:0;font-family:system-ui,Arial}#map{height:70vh}#info{padding:12px}
.sos{background:#c62828;color:#fff;padding:10px;font-weight:bold}.btn{display:inline-block;margin:6px 6px 0 0;
padding:10px 14px;border-radius:8px;background:#1f4e79;color:#fff;text-decoration:none}.red{background:#c62828}</style>
</head><body><div id="banner"></div><div id="map"></div><div id="info">Loading…</div>
<script>
const TOKEN=__TOKEN_JSON__;
const map=L.map('map').setView([20.6,78.9],5);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap'}).addTo(map);
let marker=null,line=null,first=true;
// build the page with textContent only – names come from users and must never be treated as HTML
function el(tag,text,cls,attrs){const e=document.createElement(tag);if(text!=null)e.textContent=text;if(cls)e.className=cls;
 for(const k in (attrs||{}))e.setAttribute(k,attrs[k]);return e;}
async function load(){
 const r=await fetch('/api/live/'+encodeURIComponent(TOKEN));
 const info=document.getElementById('info'),banner=document.getElementById('banner');
 if(!r.ok){let m='Link not available';try{m=(await r.json()).detail||m}catch(e){}info.textContent=m;banner.replaceChildren();return;}
 const d=await r.json();
 banner.replaceChildren(...(d.sos_active?[el('div','🚨 SOS ACTIVE – '+d.name+' needs help','sos')]:[]));
 if(typeof d.lat==='number'&&typeof d.lon==='number'){const p=[d.lat,d.lon];
  if(!marker)marker=L.marker(p).addTo(map);else marker.setLatLng(p);
  if(line)map.removeLayer(line); if(d.trail.length>1)line=L.polyline(d.trail,{color:'#2e75b6'}).addTo(map);
  if(first){map.setView(p,16);first=false;}}
 const t=d.last_seen?new Date(d.last_seen).toLocaleTimeString():'-';
 const parts=[el('b',d.name),document.createTextNode(' · updated '+t+' · battery '+(d.battery??'-')+'%'+
  (typeof d.speed_kmh==='number'?' · speed '+Math.round(d.speed_kmh)+' km/h':'')),el('br'),
  document.createTextNode('Link expires '+new Date(d.expires_at).toLocaleString()),el('br'),
  el('a','Call 112','btn red',{href:'tel:112'})];
 if(typeof d.lat==='number')parts.push(el('a','Directions','btn',{href:'https://www.google.com/maps/dir/?api=1&destination='+
  encodeURIComponent(d.lat+','+d.lon),rel:'noopener noreferrer',target:'_blank'}));
 info.replaceChildren(...parts);
}
load();setInterval(load,10000);
</script></body></html>"""


# ---------------- School safety circle ----------------
class SchoolIn(BaseModel):
    name: str


class SchoolOut(BaseModel):
    id: int
    name: str
    role: str
    status: str = "approved"
    staff_code: str | None = None
    parent_code: str | None = None


class StaffOut(BaseModel):
    user_id: int
    name: str
    phone: str | None
    email: str
    role: str
    status: str


class JoinStaffIn(BaseModel):
    staff_code: str
    role: str = "teacher"


class LinkDeviceIn(BaseModel):
    parent_code: str
    class_name: str | None = None
    share_sos: bool = True


@router.post("/schools", response_model=SchoolOut)
def create_school(body: SchoolIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = School(name=body.name.strip(), staff_code="ST" + secrets.token_hex(3).upper(),
               parent_code="PA" + secrets.token_hex(3).upper())
    db.add(s)
    db.flush()
    db.add(SchoolStaff(school_id=s.id, user_id=user.id, role="admin"))
    db.commit()
    return SchoolOut(id=s.id, name=s.name, role="admin", staff_code=s.staff_code, parent_code=s.parent_code)


@router.post("/schools/join", response_model=SchoolOut)
def join_school(body: JoinStaffIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Staff join request. Requires a verified phone (OTP). The school admin must approve (decision D1)."""
    if not user.phone_verified:
        raise HTTPException(400, "Verify your mobile number with OTP first")
    s = db.scalar(select(School).where(School.staff_code == body.staff_code.strip().upper()))
    if s is None:
        raise HTTPException(400, "Wrong staff code")
    role = body.role if body.role in ("teacher", "security", "bus") else "teacher"
    st = db.scalar(select(SchoolStaff).where(SchoolStaff.school_id == s.id, SchoolStaff.user_id == user.id))
    if st is None:
        st = SchoolStaff(school_id=s.id, user_id=user.id, role=role, status="pending")
        db.add(st)
        db.commit()
    return SchoolOut(id=s.id, name=s.name, role=st.role, status=st.status)


def _require_admin(db: Session, user: User, school_id: int) -> None:
    if not db.scalar(select(SchoolStaff).where(SchoolStaff.school_id == school_id, SchoolStaff.user_id == user.id,
                                               SchoolStaff.role == "admin")):
        raise HTTPException(403, "Only the school admin can manage staff")


@router.get("/schools/{school_id}/staff", response_model=list[StaffOut])
def list_staff(school_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _require_admin(db, user, school_id)
    rows = db.execute(select(SchoolStaff, User).join(User, SchoolStaff.user_id == User.id)
                      .where(SchoolStaff.school_id == school_id).order_by(SchoolStaff.status.desc(), User.name)).all()
    return [StaffOut(user_id=u.id, name=u.name, phone=u.phone, email=u.email, role=st.role, status=st.status)
            for st, u in rows]


@router.post("/schools/{school_id}/staff/{user_id}/approve", response_model=StaffOut)
def approve_staff(school_id: int, user_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _require_admin(db, user, school_id)
    st = db.scalar(select(SchoolStaff).where(SchoolStaff.school_id == school_id, SchoolStaff.user_id == user_id))
    if st is None:
        raise HTTPException(404, "Request not found")
    st.status = "approved"
    db.commit()
    u = db.get(User, user_id)
    from .. import notify
    notify.push([u], "School access approved", "You will now receive student SOS alerts from your school.",
                {"type": "staff_approved", "school_id": school_id})
    return StaffOut(user_id=u.id, name=u.name, phone=u.phone, email=u.email, role=st.role, status=st.status)


@router.delete("/schools/{school_id}/staff/{user_id}")
def remove_staff(school_id: int, user_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _require_admin(db, user, school_id)
    if user_id == user.id:
        raise HTTPException(400, "Admin cannot remove themselves")
    st = db.scalar(select(SchoolStaff).where(SchoolStaff.school_id == school_id, SchoolStaff.user_id == user_id))
    if st:
        db.delete(st)
        db.commit()
    return {"ok": True}


@router.get("/schools", response_model=list[SchoolOut])
def my_schools(user: User = Depends(current_user), db: Session = Depends(get_db)):
    out = []
    for st, s in db.execute(select(SchoolStaff, School).join(School).where(SchoolStaff.user_id == user.id)).all():
        admin = st.role == "admin"
        out.append(SchoolOut(id=s.id, name=s.name, role=st.role, status=st.status, staff_code=s.staff_code if admin else None,
                             parent_code=s.parent_code if admin else None))
    return out


@router.post("/devices/{device_id}/school", response_model=SchoolOut)
def link_device_to_school(device_id: str, body: LinkDeviceIn, user: User = Depends(current_user),
                          db: Session = Depends(get_db)):
    """Parent links the child's tracker to a school and gives consent for SOS sharing."""
    dev = _get_member_device(db, user, device_id)
    s = db.scalar(select(School).where(School.parent_code == body.parent_code.strip().upper()))
    if s is None:
        raise HTTPException(400, "Wrong school code")
    link = db.scalar(select(DeviceSchool).where(DeviceSchool.device_pk == dev.id, DeviceSchool.school_id == s.id))
    if link is None:
        link = DeviceSchool(device_pk=dev.id, school_id=s.id, consent_by=user.id)
        db.add(link)
    link.class_name, link.share_sos = body.class_name, body.share_sos
    db.commit()
    return SchoolOut(id=s.id, name=s.name, role="parent")


@router.delete("/devices/{device_id}/school/{school_id}")
def unlink_device(device_id: str, school_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    dev = _get_member_device(db, user, device_id)
    link = db.scalar(select(DeviceSchool).where(DeviceSchool.device_pk == dev.id, DeviceSchool.school_id == school_id))
    if link:
        db.delete(link)
        db.commit()
    return {"ok": True}


@router.get("/schools/{school_id}/sos")
def school_sos(school_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Staff view: active SOS of linked students. Location visible ONLY while an SOS is active."""
    if not db.scalar(select(SchoolStaff).where(SchoolStaff.school_id == school_id, SchoolStaff.user_id == user.id,
                                               SchoolStaff.status == "approved")):
        raise HTTPException(403, "Your staff access is waiting for the school admin's approval")
    rows = db.execute(
        select(SosEvent, Device, DeviceSchool).join(Device, SosEvent.device_pk == Device.id)
        .join(DeviceSchool, DeviceSchool.device_pk == Device.id)
        .where(DeviceSchool.school_id == school_id, DeviceSchool.share_sos.is_(True),
               SosEvent.status.in_(["active", "acknowledged"]), SosEvent.school_alerted.is_(True))
    ).all()
    from ..models import HelpRequest
    from ..services_help import device_plan
    from ..places import alerted_keys
    out = []
    for ev, dev, link in rows:
        if "school" not in alerted_keys(ev):       # sent only to e.g. the swimming coach -> not for the school
            continue
        db.add(LocationAccessLog(sos_id=ev.id, user_id=user.id, kind="school"))
        plan = device_plan(db, dev)
        group = db.scalar(select(HelpRequest).where(HelpRequest.sos_id == ev.id, HelpRequest.closed.is_(False)))
        out.append({**sos_info(dev, ev), "status": ev.status, "source": ev.source, "class_name": link.class_name,
                    "school_alerted": ev.school_notified_at is not None, "plan": plan,
                    "group_allowed": plan == "guardian", "group_started": group is not None})
    db.commit()
    return out


@router.post("/schools/{school_id}/sos/{sos_id}/group")
def school_start_group(school_id: int, sos_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Removed: only the parent can start Emergency – Group."""
    raise HTTPException(403, "Only the child's parent can start Emergency – Group.")
    if not db.scalar(select(SchoolStaff).where(SchoolStaff.school_id == school_id, SchoolStaff.user_id == user.id,
                                               SchoolStaff.status == "approved")):
        raise HTTPException(403, "Not approved staff of this school")
    ev = db.get(SosEvent, sos_id)
    if ev is None or ev.status not in ("active", "acknowledged"):
        raise HTTPException(404, "SOS not active")
    dev = db.get(Device, ev.device_pk)
    if not db.scalar(select(DeviceSchool).where(DeviceSchool.device_pk == dev.id, DeviceSchool.school_id == school_id)):
        raise HTTPException(404, "Student not linked to this school")
    from ..services_help import device_plan, start_group
    if device_plan(db, dev) != "guardian":
        raise HTTPException(402, "Emergency – Group from school is available for students on the premium (Guardian) plan.")
    r = start_group(db, dev, ev, user)
    db.commit()
    from .. import notify
    from ..services import device_users
    notify.push(device_users(db, dev), "👥 School requested group help",
                f"{user.name} (school) requested help from nearby SelfXTrack users.",
                {"type": "group_started", "sos_id": ev.id, "device_id": dev.device_id})
    return {"sos_id": ev.id, **r}
