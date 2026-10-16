"""Phase 6 – privacy (India DPDP Act 2023): export my data, delete my account, retention clean-up, policy pages."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import (AiAlert, Device, DeviceMember, Location, LocationAccessLog, OtpCode, ShareLink, SosEvent, User)
from ..security import current_user, verify_secret
from ..services import as_utc

router = APIRouter(prefix="/api/me", tags=["privacy"])
pages = APIRouter(include_in_schema=False)


def _iso(dt):
    return as_utc(dt).isoformat() if dt else None


@router.get("/export")
def export(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Everything we store about me and my children (last 30 days of locations), as JSON."""
    since = datetime.now(timezone.utc) - timedelta(days=30)
    devices = []
    for m in user.memberships:
        d = m.device
        devices.append({
            "device_id": d.device_id, "name": d.name, "kind": d.kind, "my_role": m.role,
            "school": d.manual_school, "class": d.manual_class,
            "locations_30d": [{"ts": _iso(p.ts), "lat": p.lat, "lon": p.lon, "battery": p.battery} for p in
                              db.scalars(select(Location).where(Location.device_pk == d.id, Location.ts >= since)
                                         .order_by(Location.ts)).all()],
            "sos": [{"started": _iso(s.started_at), "status": s.status, "source": s.source} for s in
                    db.scalars(select(SosEvent).where(SosEvent.device_pk == d.id)).all()],
            "alerts": [{"ts": _iso(a.ts), "kind": a.kind, "text": a.text} for a in
                       db.scalars(select(AiAlert).where(AiAlert.device_pk == d.id)).all()],
            "location_viewed_by_school_or_helpers": len(db.scalars(select(LocationAccessLog).join(
                SosEvent, SosEvent.id == LocationAccessLog.sos_id).where(SosEvent.device_pk == d.id)).all()),
        })
    return {"exported_at": datetime.now(timezone.utc).isoformat(),
            "account": {"email": user.email, "name": user.name, "phone": user.phone, "plan": user.plan,
                        "created_at": _iso(user.created_at), "consent_at": _iso(user.consent_at),
                        "terms_version": user.terms_version},
            "devices": devices}


class DeleteIn(BaseModel):
    password: str


@router.delete("")
def delete_account(body: DeleteIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Delete my account. Trackers I own are released and their history is erased; shared access is removed."""
    if not verify_secret(body.password, user.password_hash):
        raise HTTPException(403, "Wrong password")
    for m in list(user.memberships):
        d: Device = m.device
        if m.role == "owner":
            for model in (Location, AiAlert, LocationAccessLog, ShareLink):
                if model is LocationAccessLog:
                    ids = [s.id for s in db.scalars(select(SosEvent).where(SosEvent.device_pk == d.id)).all()]
                    if ids:
                        db.execute(delete(LocationAccessLog).where(LocationAccessLog.sos_id.in_(ids)))
                else:
                    db.execute(delete(model).where(model.device_pk == d.id))
            for other in list(d.members):
                db.delete(other)
            d.claimed, d.name, d.manual_school, d.manual_class = False, None, None, None
            d.last_lat = d.last_lon = None
        else:
            db.delete(m)
    db.execute(delete(OtpCode).where(OtpCode.user_id == user.id))
    user.email = f"deleted-{user.id}@deleted.invalid"
    user.name, user.phone, user.fcm_token = "Deleted user", None, None
    user.phone_verified, user.helper_available, user.helper_lat, user.helper_lon = False, False, None, None
    user.password_hash = "!"
    db.commit()
    return {"ok": True}


def cleanup(db: Session) -> dict:
    """Daily: delete location history older than the retention period (DPDP: keep only what is needed)."""
    now = datetime.now(timezone.utc)
    n1 = db.execute(delete(Location).where(Location.ts < now - timedelta(days=settings.location_retention_days))).rowcount
    n2 = db.execute(delete(LocationAccessLog).where(
        LocationAccessLog.ts < now - timedelta(days=settings.log_retention_days))).rowcount
    n3 = db.execute(delete(AiAlert).where(AiAlert.ts < now - timedelta(days=settings.log_retention_days))).rowcount
    db.commit()
    return {"locations": n1, "access_logs": n2, "alerts": n3}


_STYLE = "<style>body{font-family:system-ui,Arial;max-width:760px;margin:40px auto;padding:0 16px;line-height:1.6}h1{color:#1F4E79}</style>"


@pages.get("/privacy", response_class=HTMLResponse)
def privacy_page():
    return f"""<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">{_STYLE}
<h1>SelfXTrack – Privacy Policy (draft {settings.terms_version})</h1>
<p><b>DRAFT – to be reviewed by a lawyer before launch.</b></p>
<h3>What we collect</h3><ul><li>Parent account: name, email, mobile number (verified by OTP).</li>
<li>Tracker: location, battery, speed, SOS presses, motion/fall events, nearby school-bus beacons.</li>
<li>Names of school staff / family numbers that you add.</li></ul>
<h3>Why</h3><p>Only to keep your child or family member safe: live location for the family, SOS alerts, safe zones,
school and nearby-help escalation that <b>you</b> start or allow, and safety insights.</p>
<h3>Who can see the location</h3><ul><li>Family members you approve – always.</li>
<li>School staff whose number you added – only during an active SOS.</li>
<li>Nearby helpers – distance only, exact location only after they accept, only during that emergency.</li>
<li>Every school / helper view is logged and visible to you.</li></ul>
<h3>Storage & retention</h3><p>Data is stored in India. Location history is deleted after {settings.location_retention_days} days;
alerts and access logs after {settings.log_retention_days} days.</p>
<h3>Your rights</h3><p>Download all your data (app → Account → Export) or delete your account at any time
(app → Account → Delete). Children's data is processed only with the parent's verifiable consent.</p>
<h3>Contact</h3><p>Grievance officer: privacy@selfxtrack.in (to be confirmed).</p>"""


@pages.get("/terms", response_class=HTMLResponse)
def terms_page():
    return f"""<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">{_STYLE}
<h1>SelfXTrack – Terms of Use (draft {settings.terms_version})</h1>
<p><b>DRAFT – to be reviewed by a lawyer before launch.</b></p>
<ul><li>SelfXTrack helps families; it is <b>not</b> an emergency service. In danger, call 112.</li>
<li>GPS and mobile networks can fail or be inaccurate; alerts may be delayed.</li>
<li>Fall / inactivity detection is not a medical device.</li>
<li>AI insights are hints, never a guarantee of safety.</li>
<li>Subscriptions renew automatically and can be cancelled anytime; SOS to family keeps working even if a payment fails.</li>
<li>Do not use SelfXTrack to track anyone without their or their guardian's consent.</li></ul>"""
