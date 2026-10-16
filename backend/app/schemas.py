from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RegisterIn(BaseModel):
    email: str
    name: str
    password: str = Field(min_length=8)
    phone: str | None = None
    consent: bool = True      # parent agrees to terms + privacy policy (and consents for their child)


class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    name: str


class FcmIn(BaseModel):
    token: str


class ProvisionIn(BaseModel):
    device_id: str
    kind: str = "child"


class ProvisionOut(BaseModel):
    device_id: str
    device_secret: str
    claim_code: str


class ClaimIn(BaseModel):
    device_id: str
    claim_code: str
    name: str
    kind: str = "child"


class ShareIn(BaseModel):
    email: str


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    device_id: str
    name: str | None
    kind: str
    last_seen: datetime | None
    last_lat: float | None
    last_lon: float | None
    last_accuracy: float | None
    battery: int | None
    charging: bool
    online: bool = False
    active_sos: int | None = None


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ts: datetime
    lat: float
    lon: float
    accuracy: float | None
    speed: float | None
    heading: float | None
    battery: int | None
    source: str


class SosOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    device_id: str | None = None
    device_name: str | None = None
    started_at: datetime
    lat: float | None
    lon: float | None
    status: str
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    responder: str | None = None          # "saurav (family)" / "rupa (school)" – who is handling it
    source: str | None = None             # device = child pressed SOS · parent = parent escalated


class TelemetryIn(BaseModel):
    """Compact payload sent by the device (keeps 4G data use low)."""
    t: int | None = None  # unix seconds (device clock); server time used if missing
    lat: float | None = None
    lon: float | None = None
    acc: float | None = None  # metres
    spd: float | None = None  # km/h
    hdg: float | None = None  # degrees
    bat: int | None = None  # %
    chg: int | None = 0  # charging 0/1
    sos: int | None = 0  # 1 = SOS pressed
    src: str | None = "gnss"
    fw: str | None = None
    fall: int | None = 0          # 1 = device detected a fall (after its 30 s cancel window)
    act: int | None = None        # motion events since the last report (elderly inactivity)
    ble: list[str] | None = None  # BLE beacon IDs seen (bus check-in), e.g. ["BUS-12"]


class TelemetryAck(BaseModel):
    ok: bool = True
    interval_s: int  # how often the device should report next
    sos_active: bool
    cfg: dict | None = None   # device settings: fall detection on/off, BLE beacons to scan for
    ota: dict | None = None   # firmware update offer: version, url, sha256, size
