from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import User
from ..schemas import FcmIn, LoginIn, RegisterIn, TokenOut
from ..security import create_token, current_user, hash_secret, verify_secret

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already registered")
    if not body.consent:
        raise HTTPException(400, "Please accept the Terms and Privacy Policy to create an account")
    from datetime import datetime, timezone
    user = User(email=email, name=body.name.strip(), phone=body.phone, password_hash=hash_secret(body.password),
                plan=settings.default_plan, consent_at=datetime.now(timezone.utc), terms_version=settings.terms_version)
    db.add(user)
    db.commit()
    return TokenOut(access_token=create_token(user.id), user_id=user.id, name=user.name)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if user is None or not verify_secret(body.password, user.password_hash):
        raise HTTPException(401, "Wrong email or password")
    return TokenOut(access_token=create_token(user.id), user_id=user.id, name=user.name)


@router.post("/fcm-token")
def set_fcm(body: FcmIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.fcm_token = body.token
    db.add(user)
    db.commit()
    return {"ok": True}


class LangIn(BaseModel):
    lang: str


@router.put("/lang")
def set_lang(body: LangIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """App language of this user – server-written alerts (AI, bus, weekly) are sent in it."""
    from ..lang import norm
    user.lang = norm(body.lang)
    db.commit()
    return {"ok": True, "lang": user.lang}


@router.post("/logout")
def logout(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Stop push notifications to this phone."""
    user.fcm_token = None
    db.commit()
    return {"ok": True}
