import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import OtpCode, User
from ..security import current_user, hash_secret, verify_secret
from ..services import as_utc
from ..sms import send_sms

router = APIRouter(prefix="/api/auth", tags=["auth"])


class OtpRequest(BaseModel):
    phone: str


class OtpVerify(BaseModel):
    phone: str
    code: str


class MeOut(BaseModel):
    id: int
    name: str
    email: str
    phone: str | None
    phone_verified: bool
    plan: str = "basic"
    helper_available: bool = True


class ForgotIn(BaseModel):
    email: str


class ResetIn(BaseModel):
    email: str
    code: str
    new_password: str


def _me(u: User) -> "MeOut":
    return MeOut(id=u.id, name=u.name, email=u.email, phone=u.phone, phone_verified=u.phone_verified,
                 plan=__import__("app.plans", fromlist=["x"]).effective_plan(u), helper_available=u.helper_available)


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        digits = "91" + digits
    if not re.fullmatch(r"91[6-9]\d{9}", digits):
        raise HTTPException(400, "Enter a valid Indian mobile number")
    return "+" + digits


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(current_user)):
    return _me(user)


@router.post("/otp/request")
def otp_request(body: OtpRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    phone = normalize_phone(body.phone)
    since = datetime.now(timezone.utc) - timedelta(minutes=15)
    recent = db.scalars(select(OtpCode).where(OtpCode.user_id == user.id, OtpCode.created_at >= since)).all()
    if len(recent) >= 3:
        raise HTTPException(429, "Too many OTP requests. Try again in 15 minutes.")
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(OtpCode(user_id=user.id, phone=phone, code_hash=hash_secret(code), purpose="verify",
                   expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)))
    db.commit()
    if not send_sms(phone, f"{code} is your SelfXTrack verification code. Valid for 5 minutes. Do not share it."):
        raise HTTPException(503, "Could not send SMS. Try again.")
    out = {"ok": True, "phone": phone}
    if settings.otp_dev_mode:
        out["dev_code"] = code   # testing only – never enable in production
    return out


@router.post("/otp/verify", response_model=MeOut)
def otp_verify(body: OtpVerify, user: User = Depends(current_user), db: Session = Depends(get_db)):
    phone = normalize_phone(body.phone)
    otp = db.scalar(select(OtpCode).where(OtpCode.user_id == user.id, OtpCode.phone == phone, OtpCode.used.is_(False),
                                          OtpCode.purpose == "verify")
                    .order_by(OtpCode.created_at.desc()))
    if otp is None or as_utc(otp.expires_at) < datetime.now(timezone.utc):
        raise HTTPException(400, "OTP expired. Request a new one.")
    if otp.attempts >= 5:
        raise HTTPException(429, "Too many wrong attempts. Request a new OTP.")
    otp.attempts += 1
    if not verify_secret(body.code.strip(), otp.code_hash):
        db.commit()
        raise HTTPException(400, "Wrong OTP")
    otp.used = True
    user.phone, user.phone_verified = phone, True
    db.commit()
    _notify_family_invites(db, user)
    return _me(user)


def _notify_family_invites(db: Session, user: User):
    """Someone invited by phone just verified it -> tell the inviting parent to accept."""
    from .. import notify
    from ..models import Device, FamilyInvite
    from ..realtime import manager
    for inv in db.scalars(select(FamilyInvite).where(FamilyInvite.phone == user.phone, FamilyInvite.status == "pending")).all():
        dev = db.get(Device, inv.device_pk)
        parent = db.get(User, inv.invited_by)
        if parent and dev:
            notify.push([parent], "👪 Family request", f"{inv.name} ({user.phone}) joined SelfXTrack. Accept to share {dev.name or dev.device_id}?",
                        {"type": "family_request", "device_id": dev.device_id})
            manager.publish([parent.id], {"type": "family_request", "device_id": dev.device_id})


@router.post("/password/forgot")
def forgot(body: ForgotIn, db: Session = Depends(get_db)):
    """Sends an OTP to the account's verified mobile. Same reply whether or not the email exists."""
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    out = {"ok": True, "message": "If this account has a verified mobile, an OTP has been sent."}
    if user is None or not user.phone_verified or not user.phone:
        return out
    since = datetime.now(timezone.utc) - timedelta(minutes=15)
    if len(db.scalars(select(OtpCode).where(OtpCode.user_id == user.id, OtpCode.created_at >= since)).all()) >= 3:
        raise HTTPException(429, "Too many OTP requests. Try again in 15 minutes.")
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(OtpCode(user_id=user.id, phone=user.phone, code_hash=hash_secret(code), purpose="reset",
                   expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)))
    db.commit()
    send_sms(user.phone, f"{code} is your SelfXTrack password reset code. Valid 5 minutes.")
    if settings.otp_dev_mode:
        out["dev_code"] = code
    out["phone_hint"] = user.phone[:3] + "******" + user.phone[-2:]
    return out


@router.post("/password/reset")
def reset(body: ResetIn, db: Session = Depends(get_db)):
    if len(body.new_password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if user is None or not user.phone:
        raise HTTPException(400, "Wrong OTP")
    # only a password-reset code works here – a phone-verification code cannot reset the password
    otp = db.scalar(select(OtpCode).where(OtpCode.user_id == user.id, OtpCode.used.is_(False), OtpCode.purpose == "reset")
                    .order_by(OtpCode.created_at.desc()))
    if otp is None or as_utc(otp.expires_at) < datetime.now(timezone.utc) or otp.attempts >= 5:
        raise HTTPException(400, "OTP expired. Request a new one.")
    otp.attempts += 1
    if not verify_secret(body.code.strip(), otp.code_hash):
        db.commit()
        raise HTTPException(400, "Wrong OTP")
    otp.used = True
    user.password_hash = hash_secret(body.new_password)
    db.commit()
    return {"ok": True}
