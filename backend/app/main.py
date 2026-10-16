import asyncio
import logging

try:   # use the OS certificate store (also works behind HTTPS-inspecting proxies on office networks)
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import mqtt_bridge
from .db import ensure_schema
from .realtime import manager
from .db import SessionLocal
from .config import production_problems, settings
from .routers import admin, auth, device_api, devices, otp, phase2, phase3, phase4, phase5, privacy, web, ws
from .routers import places as places_router
from .security_mw import SecurityMiddleware
from .services import check_offline
from .services_help import check_escalations

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.env == "production":
        bad = production_problems(settings)
        if bad:
            raise RuntimeError("Unsafe production settings:\n - " + "\n - ".join(bad))
    ensure_schema()
    from . import places
    from .db import SessionLocal
    with SessionLocal() as db:
        places.migrate(db)                     # one-time move of older safe zones / school contacts / buses
    manager.loop = asyncio.get_running_loop()
    mqtt_bridge.start()
    task = asyncio.create_task(_offline_monitor()) if settings.run_monitor else None
    yield
    if task:
        task.cancel()


async def _offline_monitor():
    last_cleanup = None
    while True:
        await asyncio.sleep(60)
        try:
            with SessionLocal() as db:
                await asyncio.to_thread(check_offline, db)
                await asyncio.to_thread(check_escalations, db)
                from .ai import check_all_routines
                await asyncio.to_thread(check_all_routines, db)
                from .services_p5 import check_inactivity
                await asyncio.to_thread(check_inactivity, db)
                import datetime as _dt
                today = _dt.date.today()
                if last_cleanup != today:            # daily data-retention clean-up (DPDP)
                    await asyncio.to_thread(privacy.cleanup, db)
                    last_cleanup = today
        except Exception as e:  # keep running
            logging.getLogger("selfx").warning("offline monitor: %s", e)


app = FastAPI(title="SelfXTrack API", version="0.6.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
                   allow_methods=["*"], allow_headers=["*"])
app.add_middleware(SecurityMiddleware)
app.include_router(auth.router)
app.include_router(otp.router)
app.include_router(devices.router)
app.include_router(device_api.router)
app.include_router(ws.router)
app.include_router(phase2.router)
app.include_router(phase2.public)
app.include_router(phase3.router)
app.include_router(phase4.router)
app.include_router(phase5.router)
app.include_router(places_router.router)
app.include_router(admin.router)
app.include_router(privacy.router)
app.include_router(privacy.pages)
app.include_router(web.router)


@app.get("/", include_in_schema=False)
def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/docs")


@app.get("/health")
def health():
    return {"ok": True}
