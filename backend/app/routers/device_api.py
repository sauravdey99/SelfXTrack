"""Endpoints called by the tracker itself (HTTPS fallback when MQTT is not used)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Device
from ..schemas import TelemetryAck, TelemetryIn
from ..security import current_device
from ..services import ingest_telemetry

router = APIRouter(prefix="/api/device", tags=["device"])


@router.post("/telemetry", response_model=TelemetryAck)
def telemetry(body: TelemetryIn, dev: Device = Depends(current_device), db: Session = Depends(get_db)):
    interval, sos_on = ingest_telemetry(db, dev, body)
    from ..services_p5 import device_cfg, ota_offer
    return TelemetryAck(interval_s=interval, sos_active=sos_on, cfg=device_cfg(db, dev), ota=ota_offer(db, dev, sos_on))


@router.get("/firmware/{release_id}")
def firmware_file(release_id: int, dev: Device = Depends(current_device), db: Session = Depends(get_db)):
    """Device downloads the firmware image (supports HTTP Range for resumable downloads over 4G)."""
    from fastapi import HTTPException
    from fastapi.responses import FileResponse
    from ..models import FirmwareRelease
    from ..routers.admin import FW_DIR
    rel = db.get(FirmwareRelease, release_id)
    if rel is None or not rel.active:
        raise HTTPException(404, "Release not found")
    return FileResponse(FW_DIR / rel.filename, media_type="application/octet-stream", filename=f"selfx-{rel.version}.bin")


class OtaStatusIn(BaseModel):
    version: str
    status: str          # downloading / verifying / installed / failed:<reason>


@router.post("/ota-status")
def ota_status(body: OtaStatusIn, dev: Device = Depends(current_device), db: Session = Depends(get_db)):
    from datetime import datetime, timezone
    dev.ota_status = f"{body.version}: {body.status}"[:40]
    dev.ota_updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}
