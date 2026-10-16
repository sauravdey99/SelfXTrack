import hmac
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import Device, User

bearer = HTTPBearer(auto_error=False)


def hash_secret(raw: str) -> str:
    return bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()


def verify_secret(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode(), hashed.encode())
    except ValueError:
        return False


def create_token(user_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"sub": str(user_id), "exp": exp}, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> int:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return int(payload["sub"])
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing token")
    user = db.get(User, decode_token(creds.credentials))
    if user is None or user.password_hash == "!":          # deleted account
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


def authenticate_device(db: Session, device_id: str, secret: str) -> Device:
    dev = db.scalar(select(Device).where(Device.device_id == device_id))
    if dev is None or not verify_secret(secret, dev.secret_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Device authentication failed")
    return dev


def current_device(
    x_device_id: str = Header(...), x_device_secret: str = Header(...), db: Session = Depends(get_db)
) -> Device:
    return authenticate_device(db, x_device_id, x_device_secret)


def require_admin(x_admin_key: str = Header(...)) -> None:
    if not hmac.compare_digest(x_admin_key.encode(), settings.admin_key.encode()):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin key required")
