from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    fcm_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    plan: Mapped[str] = mapped_column(String(12), default="basic")  # basic / smart / guardian
    plan_status: Mapped[str] = mapped_column(String(12), default="free")  # free / trial / active / past_due / cancelled
    plan_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    razorpay_sub_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)   # DPDP consent
    terms_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    banned: Mapped[bool] = mapped_column(Boolean, default=False)
    lang: Mapped[str] = mapped_column(String(8), default="en")      # app language for server-written alerts
    # Helper network (Emergency – Group)
    helper_available: Mapped[bool] = mapped_column(Boolean, default=True)
    helper_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    helper_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    helper_loc_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    memberships: Mapped[list["DeviceMember"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # printed on device / QR
    secret_hash: Mapped[str] = mapped_column(String(255))  # device API secret (flashed at factory)
    claim_code: Mapped[str] = mapped_column(String(16))  # given to the customer in the box
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)  # e.g. "Riya"
    kind: Mapped[str] = mapped_column(String(20), default="child")  # child / elderly / pet / bike / bag
    claimed: Mapped[bool] = mapped_column(Boolean, default=False)

    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    battery: Mapped[int | None] = mapped_column(Integer, nullable=True)
    charging: Mapped[bool] = mapped_column(Boolean, default=False)
    low_battery_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    offline_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    last_speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_heading: Mapped[float | None] = mapped_column(Float, nullable=True)
    firmware: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Child setup – school typed by the parent when the school is not on SelfXTrack
    manual_school: Mapped[str | None] = mapped_column(String(160), nullable=True)
    manual_class: Mapped[str | None] = mapped_column(String(40), nullable=True)
    public_holidays: Mapped[bool] = mapped_column(Boolean, default=True)   # pause routine alerts on public holidays
    # Phase 5 – elderly care
    fall_detection: Mapped[bool] = mapped_column(Boolean, default=True)
    inactivity_hours: Mapped[int] = mapped_column(Integer, default=3)       # 0 = off
    active_from: Mapped[str] = mapped_column(String(5), default="08:00")
    active_to: Mapped[str] = mapped_column(String(5), default="21:00")
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    inactivity_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    # Phase 5 – OTA
    fw_channel: Mapped[str] = mapped_column(String(10), default="stable")
    ota_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ota_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Phase 5 – bus
    on_bus_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bus_missed: Mapped[int] = mapped_column(Integer, default=0)
    battery_warned_on: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # Phase 4 AI state (unusual route / stop detection)
    ai_offroute: Mapped[int] = mapped_column(Integer, default=0)
    ai_detour: Mapped[int] = mapped_column(Integer, default=0)
    ai_alert_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # "It's OK" on a route alert / "Pause route alerts": no route-type alerts until this time
    route_ok_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    route_ok_by: Mapped[int | None] = mapped_column(Integer, nullable=True)        # user who paused
    route_ok_trip: Mapped[bool] = mapped_column(Boolean, default=True)             # True = ends at the next known place
    stop_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stop_alerted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    members: Mapped[list["DeviceMember"]] = relationship(back_populates="device", cascade="all, delete-orphan")


class DeviceMember(Base):
    """Links family members (app users) to a device."""
    __tablename__ = "device_members"
    __table_args__ = (UniqueConstraint("device_pk", "user_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_pk: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20), default="owner")  # owner / family

    device: Mapped[Device] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


class Location(Base):
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_pk: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed: Mapped[float | None] = mapped_column(Float, nullable=True)  # km/h
    heading: Mapped[float | None] = mapped_column(Float, nullable=True)  # degrees
    battery: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(10), default="gnss")  # gnss / wifi / cell


class SosEvent(Base):
    __tablename__ = "sos_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_pk: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active / acknowledged / resolved / cancelled
    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(String(10), default="device")  # device (child pressed) / parent (escalated)
    school_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # True only when the school was really alerted (parent pressed Emergency – School, or nobody in the family
    # responded in time). Staff see an SOS only then – a buzzer press alone goes to the family only.
    school_alerted: Mapped[bool] = mapped_column(Boolean, default=False)
    # who was alerted: JSON list of "school" and/or "place:<id>" – each caretaker sees only SOS sent to them
    alerted_to: Mapped[str | None] = mapped_column(Text, nullable=True)
    family_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    escalated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # parent who alerted school/group


# ---------------- Phase 2 ----------------
class Geofence(Base):
    """A place the child goes to (home, school, tuition, swimming, grandma's …). Alerts on enter / exit, and – when
    it has a schedule – if the child is late or leaves early. Called "safe zone" in older app versions."""
    __tablename__ = "geofences"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_pk: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    radius_m: Mapped[int] = mapped_column(Integer, default=150)
    notify_enter: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_exit: Mapped[bool] = mapped_column(Boolean, default=True)
    inside: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # last known state
    kind: Mapped[str] = mapped_column(String(16), default="other")      # home/school/class/activity/family/other
    note: Mapped[str | None] = mapped_column(String(120), nullable=True)   # e.g. class 5A, "gate 2"
    # time slots: [{"days":[0-6 Mon..Sun], "start":"HH:MM", "end":"HH:MM"}] – empty = no fixed times
    schedule: Mapped[str | None] = mapped_column(Text, nullable=True)
    alert_late: Mapped[bool] = mapped_column(Boolean, default=True)      # late / left-early alerts for the slots
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ShareLink(Base):
    """Temporary live-location link for people without the app (relatives, police)."""
    __tablename__ = "share_links"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_pk: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    sos_id: Mapped[int | None] = mapped_column(ForeignKey("sos_events.id"), nullable=True)  # auto-stop when resolved


class School(Base):
    __tablename__ = "schools"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    staff_code: Mapped[str] = mapped_column(String(16), unique=True)   # teachers/staff join with this
    parent_code: Mapped[str] = mapped_column(String(16), unique=True)  # parents link a child with this
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SchoolStaff(Base):
    __tablename__ = "school_staff"
    __table_args__ = (UniqueConstraint("school_id", "user_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="teacher")  # admin / teacher / security / bus
    status: Mapped[str] = mapped_column(String(12), default="approved")  # pending / approved
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=utcnow)


class DeviceSchool(Base):
    """A child's tracker linked to a school (with parent consent)."""
    __tablename__ = "device_schools"
    __table_args__ = (UniqueConstraint("device_pk", "school_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_pk: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    class_name: Mapped[str | None] = mapped_column(String(40), nullable=True)
    consent_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    share_sos: Mapped[bool] = mapped_column(Boolean, default=True)  # school receives SOS alerts


class OtpCode(Base):
    """One-time phone verification codes (hashed, 5-minute expiry, max 5 attempts)."""
    __tablename__ = "otp_codes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    phone: Mapped[str] = mapped_column(String(20))
    code_hash: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    purpose: Mapped[str] = mapped_column(String(10), default="verify")   # verify (phone) / reset (password)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------- Phase 3 ----------------
class FamilyInvite(Base):
    """Parent invites a family member by mobile number. When that person registers + verifies the same
    number, the parent sees 'ready' and taps Accept to give them access to the child."""
    __tablename__ = "family_invites"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_pk: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending / accepted
    relation: Mapped[str] = mapped_column(String(10), default="family")  # parent (rings at once) / family (after 2 min)
    invited_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TeacherContact(Base):
    """Teacher / staff contacts added manually by a parent when the school is not on SelfXTrack."""
    __tablename__ = "teacher_contacts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_pk: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str] = mapped_column(String(20))
    role: Mapped[str] = mapped_column(String(20), default="teacher")     # teacher/staff/coach/tutor/caretaker/other
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # the place this person is responsible at (None = older school contacts not linked to a place yet)
    place_id: Mapped[int | None] = mapped_column(ForeignKey("geofences.id", ondelete="CASCADE"), nullable=True,
                                                 index=True)


class HelpRequest(Base):
    """Emergency – Group: request to nearby SelfXTrack users."""
    __tablename__ = "help_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sos_id: Mapped[int] = mapped_column(ForeignKey("sos_events.id", ondelete="CASCADE"), index=True)
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    radius_m: Mapped[int] = mapped_column(Integer, default=1000)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expanded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed: Mapped[bool] = mapped_column(Boolean, default=False)


class HelperResponse(Base):
    __tablename__ = "helper_responses"
    __table_args__ = (UniqueConstraint("help_id", "user_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    help_id: Mapped[int] = mapped_column(ForeignKey("help_requests.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(12), default="notified")  # notified / accepted / declined
    notified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LocationAccessLog(Base):
    """Every time someone outside the family sees a child's location during an emergency."""
    __tablename__ = "location_access_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sos_id: Mapped[int] = mapped_column(ForeignKey("sos_events.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))  # helper / school / link
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AbuseReport(Base):
    __tablename__ = "abuse_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reported_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    sos_id: Mapped[int | None] = mapped_column(ForeignKey("sos_events.id"), nullable=True)
    reason: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------- Phase 4 ----------------
class RouteModel(Base):
    """Learned routine of a tracker: usual grid cells (corridor) + frequent places. Rebuilt daily."""
    __tablename__ = "route_models"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_pk: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), unique=True)
    cells: Mapped[str] = mapped_column(Text, default="[]")     # JSON list of "i:j"
    extra_cells: Mapped[str | None] = mapped_column(Text, nullable=True)  # added by a parent ("regular route") – kept on relearn
    places: Mapped[str] = mapped_column(Text, default="[]")    # JSON list of places
    trips: Mapped[str] = mapped_column(Text, default="{}")     # JSON: learned trips A->B (durations, times, weekdays)
    days: Mapped[int] = mapped_column(Integer, default=0)      # distinct days of data used
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Holiday(Base):
    """Day off for a child: routine alerts (late / didn't leave / missed) pause; safety alerts continue.
    Holiday days are also left out of route learning."""
    __tablename__ = "holidays"
    __table_args__ = (UniqueConstraint("device_pk", "day"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_pk: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    day: Mapped[str] = mapped_column(String(10))           # YYYY-MM-DD (local)
    note: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class AiAlert(Base):
    """Advisory alerts (never SOS): unusual route / unknown stop / risk prompt."""
    __tablename__ = "ai_alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_pk: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(String(300))                  # English
    msg_args: Mapped[str | None] = mapped_column(Text, nullable=True)  # values to re-render in other languages
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan: Mapped[str] = mapped_column(String(12))
    period: Mapped[str] = mapped_column(String(8))          # monthly / yearly
    amount_inr: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default="created")  # created / paid / failed
    razorpay_sub_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------- Phase 5 ----------------
class FirmwareRelease(Base):
    __tablename__ = "firmware_releases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(32))
    channel: Mapped[str] = mapped_column(String(10), default="stable")      # stable / beta
    filename: Mapped[str] = mapped_column(String(200))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    rollout_percent: Mapped[int] = mapped_column(Integer, default=100)       # staged rollout
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Bus(Base):
    """School bus / van with a BLE beacon. Added by a parent (or school) with the beacon ID printed on it."""
    __tablename__ = "buses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    beacon_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Transport(Base):
    """How the child travels: school bus, van, auto, cab … Optional BLE beacon (then a Bus + DeviceBus link exists
    and "boarded / got off" alerts work), optional driver, and the places it is used for."""
    __tablename__ = "transports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_pk: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(10), default="bus")          # bus/van/auto/cab/other
    bus_id: Mapped[int | None] = mapped_column(ForeignKey("buses.id", ondelete="SET NULL"), nullable=True)
    driver_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    driver_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    place_ids: Mapped[str | None] = mapped_column(Text, nullable=True)    # JSON list of Geofence ids
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DeviceBus(Base):
    __tablename__ = "device_buses"
    __table_args__ = (UniqueConstraint("device_pk", "bus_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_pk: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    bus_id: Mapped[int] = mapped_column(ForeignKey("buses.id", ondelete="CASCADE"))


class BusEvent(Base):
    __tablename__ = "bus_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_pk: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    bus_id: Mapped[int] = mapped_column(ForeignKey("buses.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(8))              # board / alight
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
