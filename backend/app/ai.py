"""Phase 4 AI – deterministic statistics on the server (route learning, anomalies, ETA, summaries).
The Claude API (llm.py) is optional and only rewrites/answers from the verified facts computed here.
Safety rule: these are ADVISORY alerts to the family. They never raise an SOS or alert helpers."""
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from statistics import median
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import llm, notify
from .config import settings
from . import push_msgs
from .models import (AiAlert, Device, Geofence, Holiday, HelperResponse, HelpRequest, Location, LocationAccessLog,
                     RouteModel, SosEvent, User)
from .realtime import manager
from .services import as_utc, distance_m

log = logging.getLogger("selfx.ai")

CELL = 0.0015            # ~165 m grid used for the "usual corridor"
STOP_RADIUS_M = 120
STOP_MIN_MINUTES = 8
PLACE_MERGE_M = 150


def tz() -> ZoneInfo:
    return ZoneInfo(settings.local_timezone)


def local(dt: datetime) -> datetime:
    return as_utc(dt).astimezone(tz())


def hhmm(dt: datetime) -> str:
    return local(dt).strftime("%H:%M")


def cell(lat: float, lon: float) -> tuple[int, int]:
    return int(round(lat / CELL)), int(round(lon / CELL))


def _key(c: tuple[int, int]) -> str:
    return f"{c[0]}:{c[1]}"


# ---------------- learning ----------------
def path_km(pts: list) -> float:
    """Distance along the reports, ignoring GPS jumps (steps much faster than the measured speed)."""
    km = 0.0
    for a, b in zip(pts, pts[1:]):
        d = distance_m(a.lat, a.lon, b.lat, b.lon)
        dt = abs((as_utc(b.ts) - as_utc(a.ts)).total_seconds())
        # GPS jump: much faster than the speed the tracker itself measured (walking 5 km/h -> limit 40 km/h)
        limit = min(150, max(40, 2.5 * (b.speed or 0) + 20))
        if d <= 30 or (dt > 0 and d / dt * 3.6 <= limit):
            km += d
    return km / 1000


def detect_stops(points: list[Location]) -> list[dict]:
    """A stop = consecutive reports within 120 m for at least 8 minutes."""
    stops, group = [], []

    def close():
        if len(group) >= 2:
            dur = (as_utc(group[-1].ts) - as_utc(group[0].ts)).total_seconds() / 60
            if dur >= STOP_MIN_MINUTES:
                stops.append({"lat": sum(p.lat for p in group) / len(group), "lon": sum(p.lon for p in group) / len(group),
                              "start": as_utc(group[0].ts), "end": as_utc(group[-1].ts), "minutes": round(dur)})

    for p in points:
        if group and distance_m(group[0].lat, group[0].lon, p.lat, p.lon) > STOP_RADIUS_M:
            close()
            group = []
        group.append(p)
    close()
    return stops


def _geofence_name(db: Session, dev: Device, lat: float, lon: float) -> str | None:
    for g in db.scalars(select(Geofence).where(Geofence.device_pk == dev.id)).all():
        if distance_m(lat, lon, g.lat, g.lon) <= g.radius_m + 75:
            return g.name
    return None


def holidays(db: Session, dev: Device) -> set[str]:
    from .holidays_in import HOLIDAYS
    own = set(db.scalars(select(Holiday.day).where(Holiday.device_pk == dev.id)).all())
    return own | (set(HOLIDAYS) if dev.public_holidays is not False else set())


def is_holiday(db: Session, dev: Device, day: date) -> bool:
    """Parent-set holiday, or an Indian public holiday (unless the parent switched the calendar off)."""
    from .holidays_in import public_holiday
    if dev.public_holidays is not False and public_holiday(day.isoformat()):
        return True
    return db.scalar(select(Holiday).where(Holiday.device_pk == dev.id, Holiday.day == day.isoformat())) is not None


def learn(db: Session, dev: Device) -> RouteModel:
    since = datetime.now(timezone.utc) - timedelta(days=settings.ai_learn_days)
    off = holidays(db, dev)
    pts = [p for p in db.scalars(select(Location).where(Location.device_pk == dev.id, Location.ts >= since)
                                 .order_by(Location.ts)).all()
           if local(p.ts).date().isoformat() not in off]          # holidays don't disturb the routine
    days_per_cell: dict[str, set] = {}
    hours_per_cell: dict[str, set] = {}
    days = set()
    for p in pts:
        d = local(p.ts).date()
        days.add(d)
        k = _key(cell(p.lat, p.lon))
        days_per_cell.setdefault(k, set()).add(d)
        hours_per_cell.setdefault(k, set()).add(local(p.ts).hour)
    need = 2 if len(days) >= 3 else 1
    usual = sorted(k for k, ds in days_per_cell.items() if len(ds) >= need)
    cell_hours = {k: sorted(hours_per_cell[k]) for k in usual}

    places: list[dict] = []
    for s in detect_stops(pts):
        pl = next((x for x in places if distance_m(x["lat"], x["lon"], s["lat"], s["lon"]) <= PLACE_MERGE_M), None)
        if pl is None:
            pl = {"lat": s["lat"], "lon": s["lon"], "visits": 0, "days": set(), "arrivals": [], "stays": []}
            places.append(pl)
        n = pl["visits"]
        pl["lat"] = (pl["lat"] * n + s["lat"]) / (n + 1)
        pl["lon"] = (pl["lon"] * n + s["lon"]) / (n + 1)
        pl["visits"] += 1
        pl["days"].add(local(s["start"]).date())
        st = local(s["start"])
        pl["arrivals"].append(st.hour * 60 + st.minute)
        pl["stays"].append(s["minutes"])
    out = []
    for i, pl in enumerate(sorted(places, key=lambda x: -x["visits"])):
        if pl["visits"] < 2 and len(days) >= 3:
            continue
        m = int(median(pl["arrivals"]))
        out.append({"name": _geofence_name(db, dev, pl["lat"], pl["lon"]) or f"Frequent place {i + 1}",
                    "lat": round(pl["lat"], 6), "lon": round(pl["lon"], 6), "visits": pl["visits"],
                    "days": len(pl["days"]), "usual_arrival": f"{m // 60:02d}:{m % 60:02d}",
                    "avg_stay_min": round(sum(pl["stays"]) / len(pl["stays"]))})

    trips = learn_trips(db, dev, pts, out, days)
    model = db.scalar(select(RouteModel).where(RouteModel.device_pk == dev.id))
    if model is None:
        model = RouteModel(device_pk=dev.id)
        db.add(model)
    model.cells, model.places, model.days = json.dumps(usual), json.dumps(out), len(days)
    trips["cell_hours"] = cell_hours
    model.trips = json.dumps(trips)
    model.updated_at = datetime.now(timezone.utc)
    db.flush()
    return model


def _mm(minutes: float) -> str:
    m = int(round(minutes)) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def _pctl(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def learn_trips(db: Session, dev: Device, pts: list[Location], places: list[dict], days: set) -> dict:
    """Trips between named places (A -> B): how long they take, when they start/end, on which weekdays."""
    by_day: dict[date, list[Location]] = {}
    for p in pts:
        by_day.setdefault(local(p.ts).date(), []).append(p)
    agg: dict[tuple[str, str], dict] = {}
    for day, dpts in by_day.items():
        named = [(place_name(db, dev, s["lat"], s["lon"], places), s) for s in detect_stops(dpts)]
        named = [(n, s) for n, s in named if n]
        for (a, sa), (b, sb) in zip(named, named[1:]):
            if a == b:
                continue
            dur = (sb["start"] - sa["end"]).total_seconds() / 60
            if not 1 <= dur <= 180:
                continue
            e = agg.setdefault((a, b), {"durs": [], "dep": [], "arr": [], "days": set(), "wd": {},
                                        "cells": {}, "speeds": []})
            seg = [p for p in dpts if sa["end"] <= as_utc(p.ts) <= sb["start"]]
            for k in {_key(cell(p.lat, p.lon)) for p in seg}:
                e["cells"][k] = e["cells"].get(k, 0) + 1
            e["speeds"] += [p.speed for p in seg if p.speed]
            dep, arr = local(sa["end"]), local(sb["start"])
            e["durs"].append(dur)
            e["dep"].append(dep.hour * 60 + dep.minute)
            e["arr"].append(arr.hour * 60 + arr.minute)
            if day not in e["days"]:
                e["days"].add(day)
                e["wd"][str(day.weekday())] = e["wd"].get(str(day.weekday()), 0) + 1
    wd_days: dict[str, int] = {}
    for d in days:
        wd_days[str(d.weekday())] = wd_days.get(str(d.weekday()), 0) + 1
    return {"wd_days": wd_days, "total_days": len(days), "trips": [
        {"from": a, "to": b, "count": len(e["durs"]), "days": len(e["days"]), "wd": e["wd"],
         "median_min": round(median(e["durs"])), "p80_min": round(_pctl(e["durs"], 0.8)),
         "usual_depart": _mm(median(e["dep"])), "usual_arrive": _mm(median(e["arr"])),
         "depart_spread": round(_pctl(e["dep"], 0.8) - _pctl(e["dep"], 0.2)),
         "path": sorted(e["cells"]),                       # every cell this trip has used
         "speed_med": round(median(e["speeds"]), 1) if e["speeds"] else None,
         "speed_p90": round(_pctl(e["speeds"], 0.9), 1) if e["speeds"] else None}
        for (a, b), e in agg.items() if len(e["durs"]) >= 2]}


def _routine_today(tm: dict, t: dict, day: date) -> bool:
    """Is this trip part of the routine on this weekday? (≥60 % of such days)"""
    if tm.get("total_days", 0) >= 14:
        occ = tm["wd_days"].get(str(day.weekday()), 0)
        return occ >= 2 and t["wd"].get(str(day.weekday()), 0) / occ >= 0.6
    return tm.get("total_days", 0) > 0 and t["days"] / tm["total_days"] >= 0.6


def _min_of(hm: str) -> int:
    h, m = hm.split(":")
    return int(h) * 60 + int(m)


def get_model(db: Session, dev: Device, max_age_hours: int = 24) -> RouteModel:
    model = db.scalar(select(RouteModel).where(RouteModel.device_pk == dev.id))
    if model is None or as_utc(model.updated_at) < datetime.now(timezone.utc) - timedelta(hours=max_age_hours):
        model = learn(db, dev)
    return model


def place_name(db: Session, dev: Device, lat: float, lon: float, places: list[dict] | None = None) -> str | None:
    name = _geofence_name(db, dev, lat, lon)
    if name:
        return name
    for pl in places or []:
        if distance_m(lat, lon, pl["lat"], pl["lon"]) <= 200:
            return pl["name"]
    return None


# ---------------- live checks (called on each location report) ----------------
# alerts a parent can silence with "It's OK" / "Pause route alerts" – never SOS, fall, offline, battery, schedules.
# "late" / "missed" belong here too: once the parent knows where the child is going, "hasn't reached Home" is noise.
ROUTE_KINDS = {"route", "detour", "stop", "linger", "time", "speed", "late", "missed"}


def route_paused(dev: Device, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return dev.route_ok_until is not None and as_utc(dev.route_ok_until) > now


def _end_trip_pause(db: Session, dev: Device, lat: float, lon: float, now: datetime) -> None:
    """A trip-only "It's OK" ends when the child is at one of their places again (or when it expires)."""
    if dev.route_ok_until is None:
        return
    if as_utc(dev.route_ok_until) <= now:
        dev.route_ok_until = None
        return
    if dev.route_ok_trip and any(distance_m(lat, lon, p["lat"], p["lon"]) <= p["r"] for p in _known_places(db, dev)):
        dev.route_ok_until = None


def extra_cells(model: RouteModel) -> set[str]:
    return set(json.loads(model.extra_cells or "[]"))


def learn_now(db: Session, dev: Device, since: datetime) -> int:
    """"This is a regular route": the cells visited since `since` count as usual right away (kept on relearn)."""
    model = get_model(db, dev)
    pts = db.scalars(select(Location).where(Location.device_pk == dev.id, Location.ts >= since)).all()
    cells = extra_cells(model) | {_key(cell(p.lat, p.lon)) for p in pts}
    model.extra_cells = json.dumps(sorted(cells))
    return len(pts)


def _alert(db: Session, dev: Device, users: list[User], kind: str, **p):
    """Store + send an advisory alert. Text comes from push_msgs (key = kind), in each recipient's language."""
    if kind in ROUTE_KINDS and route_paused(dev):
        return                                  # parent said this trip is fine
    p.setdefault("label", dev.name or dev.device_id)
    title, text = push_msgs.render(kind, "en", **p)
    db.add(AiAlert(device_pk=dev.id, kind=kind, text=text, msg_args=push_msgs.args_json(**p),
                   lat=dev.last_lat, lon=dev.last_lon))
    if kind in ("route", "stop", "risk"):          # routine alerts have their own once-per-trip/day rule
        dev.ai_alert_at = datetime.now(timezone.utc)
    db.flush()
    push_msgs.push(users, kind, {"type": "ai_alert", "kind": kind, "device_id": dev.device_id, "text": text,
                                 "name": p["label"]}, **p)
    for lang, ids in _by_lang(users).items():
        manager.publish(ids, {"type": "ai_alert", "kind": kind, "device_id": dev.device_id,
                              "text": push_msgs.render(kind, lang, **p)[1]})


def _by_lang(users: list[User]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for u in users:
        out.setdefault(getattr(u, "lang", None) or "en", []).append(u.id)
    return out


def check(db: Session, dev: Device, users: list[User], lat: float, lon: float, spd: float | None,
          ts: datetime, plan: str):
    from .plans import allows
    label = dev.name or dev.device_id
    _end_trip_pause(db, dev, lat, lon, as_utc(ts))
    model = get_model(db, dev)
    ready = model.days >= settings.ai_min_days
    usual = set(json.loads(model.cells)) | extra_cells(model)
    places = json.loads(model.places)
    cooldown_ok = dev.ai_alert_at is None or \
        as_utc(dev.ai_alert_at) < datetime.now(timezone.utc) - timedelta(minutes=settings.ai_alert_cooldown_minutes)
    in_zone = any(g.inside for g in db.scalars(select(Geofence).where(Geofence.device_pk == dev.id)).all())
    st = trip_state(db, dev, as_utc(ts)) if ready else None
    trip = st.get("trip") if st and st.get("state") == "moving" else None
    # heading to a place that is on the schedule now (Places): a new road there is expected, not "unusual"
    to_schedule = bool(trip and trip.get("scheduled"))
    # one alert per trip: "took a different way" already sent -> no extra "unusual route"
    told = bool(trip and _alerted_since(db, dev, "detour", as_utc(st["departed"]), ""))

    # 1) unusual route
    ci, cj = cell(lat, lon)
    off = ready and not in_zone and not any(_key((ci + a, cj + b)) in usual for a in (-1, 0, 1) for b in (-1, 0, 1))
    dev.ai_offroute = (dev.ai_offroute or 0) + 1 if off else 0
    if off and dev.ai_offroute >= settings.ai_offroute_points and cooldown_ok and not to_schedule and not told:
        near = min((distance_m(lat, lon, int(k.split(":")[0]) * CELL, int(k.split(":")[1]) * CELL) for k in usual),
                   default=0)
        late = local(ts).hour >= 20 or local(ts).hour < 6
        if allows(plan, "risk") and (spd or 0) > 25 and late:
            _alert(db, dev, users, "risk", speed=int(spd), time=hhmm(ts), near=int(near))
        else:
            _alert(db, dev, users, "route", near=int(near), time=hhmm(ts))
        cooldown_ok = False

    # 1b) usual road at an unusual time (e.g. school road at 21:00) – only while moving
    cell_hours = json.loads(model.trips or "{}").get("cell_hours", {})
    k = _key((ci, cj))
    hrs = cell_hours.get(k)
    h = local(ts).hour
    if ready and not off and not in_zone and hrs and (spd or 0) >= 3 and cooldown_ok and not to_schedule and \
            place_name(db, dev, lat, lon, places) is None and \
            min(min(abs(h - x), 24 - abs(h - x)) for x in hrs) > 2:
        _alert(db, dev, users, "time", h1=f"{hrs[0]:02d}", h2=f"{hrs[-1]:02d}", time=hhmm(ts))
        cooldown_ok = False

    # 2) long stop at an unknown place
    if dev.stop_lat is None or distance_m(dev.stop_lat, dev.stop_lon, lat, lon) > 80:
        dev.stop_lat, dev.stop_lon, dev.stop_since, dev.stop_alerted = lat, lon, ts, False
    elif not dev.stop_alerted:
        mins = (as_utc(ts) - as_utc(dev.stop_since)).total_seconds() / 60
        if mins >= settings.ai_unknown_stop_minutes:
            dev.stop_alerted = True
            if ready and not in_zone and place_name(db, dev, lat, lon, places) is None and cooldown_ok:
                _alert(db, dev, users, "stop", mins=int(mins), since=hhmm(dev.stop_since))

    # 3-5) routine: late arrival / did not leave / missed place
    db.flush()
    check_routine(db, dev, users, ts)


# ---------------- trip state + ETA ----------------
def trip_state(db: Session, dev: Device, now: datetime | None = None) -> dict | None:
    """Where is the child in the routine right now? at a place / travelling from A (to predicted B)."""
    now = now or datetime.now(timezone.utc)
    if dev.last_lat is None:
        return None
    model = get_model(db, dev)
    places, tm = json.loads(model.places), json.loads(model.trips or "{}")
    here = place_name(db, dev, dev.last_lat, dev.last_lon, places)
    if here:
        nxt = [t for t in tm.get("trips", []) if t["from"] == here and _routine_today(tm, t, local(now).date())
               and _min_of(t["usual_depart"]) >= local(now).hour * 60 + local(now).minute - 30]
        nxt.sort(key=lambda t: _min_of(t["usual_depart"]))
        return {"state": "at", "place": here, "next": nxt[0] if nxt else None}
    day0 = datetime.combine(local(now).date(), datetime.min.time(), tz()).astimezone(timezone.utc)
    pts = db.scalars(select(Location).where(Location.device_pk == dev.id, Location.ts >= day0, Location.ts <= now)
                     .order_by(Location.ts)).all()
    named = [(place_name(db, dev, s_["lat"], s_["lon"], places), s_) for s_ in detect_stops(pts)]
    named = [(n, s_) for n, s_ in named if n]
    if not named:
        return {"state": "moving", "from": None}
    origin, stop = named[-1]
    dep = stop["end"]
    dep_min = local(dep).hour * 60 + local(dep).minute
    cands = [t for t in tm.get("trips", []) if t["from"] == origin]
    best, best_score = None, 1e9
    for t in cands:            # the trip that usually starts around this time, heading the right way
        pl = next((p for p in places if p["name"] == t["to"]), None) or _gf(db, dev, t["to"])
        if pl is None:
            continue
        score = abs(_min_of(t["usual_depart"]) - dep_min) - 5 * t["count"]
        d_now = distance_m(dev.last_lat, dev.last_lon, pl["lat"], pl["lon"])
        d_dep = distance_m(stop["lat"], stop["lon"], pl["lat"], pl["lon"])
        if d_now > d_dep + 200:       # moving away from it
            score += 500
        if score < best_score:
            best, best_score = {**t, "lat": pl["lat"], "lon": pl["lon"]}, score
    if best is None or distance_m(dev.last_lat, dev.last_lon, best["lat"], best["lon"]) > \
            distance_m(stop["lat"], stop["lon"], best["lat"], best["lon"]) + 200:
        # the usual destination is behind him: clearly heading to another of his places (School -> Swimming)
        best = _approaching_place(db, dev, origin, stop, cands) or best
    best = _scheduled_trip(db, dev, origin, stop, dep, cands) or best
    return {"state": "moving", "from": origin, "departed": dep, "trip": best}


def _approaching_place(db: Session, dev: Device, origin: str, stop: dict, cands: list[dict]) -> dict | None:
    best = None
    for g in db.scalars(select(Geofence).where(Geofence.device_pk == dev.id)).all():
        d0 = distance_m(stop["lat"], stop["lon"], g.lat, g.lon)
        d1 = distance_m(dev.last_lat, dev.last_lon, g.lat, g.lon)
        if g.name != origin and d0 - d1 > 300 and (best is None or d1 < best[0]):
            best = (d1, g)
    if best is None:
        return None
    g = best[1]
    learned = next((t for t in cands if t["to"] == g.name), None)
    return {**(learned or {"from": origin, "to": g.name, "path": [], "count": 0}), "lat": g.lat, "lon": g.lon}


def _scheduled_trip(db: Session, dev: Device, origin: str, stop: dict, dep: datetime, cands: list[dict]) -> dict | None:
    """The parent's schedule (Places) beats the learned guess: left School at 16:00 and Swimming starts at 16:30
    -> the child is going to Swimming, not Home. Only if the child is not moving away from it."""
    from . import places as P
    dep_l = local(dep)
    dep_min = dep_l.hour * 60 + dep_l.minute
    best = None
    for g in db.scalars(select(Geofence).where(Geofence.device_pk == dev.id)).all():
        if g.name == origin:
            continue
        for sl in P.slots_on(g, dep_l.date()):
            start = _min_of(sl["start"])
            if not dep_min - 15 <= start <= dep_min + 90:          # a slot starting soon after leaving
                continue
            if distance_m(dev.last_lat, dev.last_lon, g.lat, g.lon) > \
                    distance_m(stop["lat"], stop["lon"], g.lat, g.lon) + 200:
                continue                                           # going somewhere else -> schedule alert handles it
            if best is None or start < best[0]:
                best = (start, g)
    if best is None:
        return None
    g = best[1]
    learned = next((t for t in cands if t["to"] == g.name), None)  # learned path to it, if there is one
    return {**(learned or {"from": origin, "to": g.name, "path": [], "count": 0}),
            "lat": g.lat, "lon": g.lon, "scheduled": True}


def _gf(db: Session, dev: Device, name: str) -> dict | None:
    g = db.scalar(select(Geofence).where(Geofence.device_pk == dev.id, Geofence.name == name))
    return {"lat": g.lat, "lon": g.lon} if g else None


def _live_minutes(db: Session, dev: Device, d: float) -> int | None:
    recent = db.scalars(select(Location).where(Location.device_pk == dev.id, Location.ts >= datetime.now(timezone.utc)
                                               - timedelta(minutes=10))).all()
    speeds = [p.speed for p in recent if p.speed]
    v = (sum(speeds) / len(speeds)) if speeds else (dev.last_speed or 0)
    return max(1, round(d * 1.3 / 1000 / v * 60)) if v >= 2 else None    # 1.3 = roads are not straight


def eta(db: Session, dev: Device) -> dict | None:
    """Expected arrival: learned trip time (\"usually 25 min\") blended with live speed."""
    if dev.last_seen is None or as_utc(dev.last_seen) < datetime.now(timezone.utc) - timedelta(minutes=30):
        return None
    st = trip_state(db, dev)
    if st is None:
        return None
    now = datetime.now(timezone.utc)
    if st["state"] == "at":
        n = st.get("next")
        txt = f"At {st['place']}"
        if n:
            txt += f" · usually leaves ~{n['usual_depart']} → {n['to']} by ~{n['usual_arrive']}"
        return {"to": st["place"], "minutes": 0, "distance_m": 0, "text": txt, "state": "at"}
    t = st.get("trip")
    if t is None:
        return {"to": None, "minutes": None, "distance_m": None, "state": "moving",
                "text": f"On the move{' from ' + st['from'] if st.get('from') else ''} – destination not clear yet"}
    d = distance_m(dev.last_lat, dev.last_lon, t["lat"], t["lon"])
    learned = as_utc(st["departed"]) + timedelta(minutes=t["median_min"])
    live = _live_minutes(db, dev, d)
    arrive = learned if learned > now else now + timedelta(minutes=live or 5)
    if live is not None and now + timedelta(minutes=live) > arrive + timedelta(minutes=10):
        arrive = now + timedelta(minutes=live)          # clearly slower than usual today
    mins = max(1, round((arrive - now).total_seconds() / 60))
    return {"to": t["to"], "minutes": mins, "distance_m": int(d), "state": "moving", "arrive_at": hhmm(arrive),
            "usual_min": t["median_min"],
            "text": f"{t['to']} by {hhmm(arrive)} (~{mins} min) · left {st['from']} {hhmm(st['departed'])}, "
                    f"usually {t['median_min']} min"}


# ---------------- live trip (works before the routine is learned) ----------------
def live_trip(db: Session, dev: Device, lang: str = "en", now: datetime | None = None) -> dict | None:
    """Current journey from the location history: where/when it started, distance so far, likely destination + ETA.
    A "stop" = 8+ min within 120 m; the trip starts at the first report after the last stop."""
    from . import geo
    now = now or datetime.now(timezone.utc)
    if dev.last_seen is None or as_utc(dev.last_seen) < now - timedelta(minutes=settings.offline_after_minutes):
        return None
    pts = db.scalars(select(Location).where(Location.device_pk == dev.id, Location.ts >= now - timedelta(hours=6))
                     .order_by(Location.ts)).all()
    if len(pts) < 2:
        return None
    cur = pts[-1]
    if (dev.last_speed or 0) < 3 and distance_m(pts[-2].lat, pts[-2].lon, cur.lat, cur.lon) < 30:
        return None                                    # not moving right now
    j, start_i = len(pts) - 1, 0
    while j > 0:
        k = j
        while k > 0 and distance_m(pts[k - 1].lat, pts[k - 1].lon, pts[j].lat, pts[j].lon) <= 120:
            k -= 1
        if as_utc(pts[j].ts) - as_utc(pts[k].ts) >= timedelta(minutes=8):
            start_i = j                                # pts[j] = last point of the stay, trip starts after it
            break
        j = k - 1 if k < j else j - 1
    origin, first = pts[start_i], pts[min(start_i + 1, len(pts) - 1)]
    km = path_km(pts[start_i:])
    mins = max(0.0, (as_utc(cur.ts) - as_utc(first.ts)).total_seconds() / 60)
    avg = km / (mins / 60) if mins >= 2 else (dev.last_speed or 0)
    speed = max(avg if avg > 1 else (dev.last_speed or 0), 3.0)         # km/h used for the estimate
    places = _known_places(db, dev)

    def name_at(lat, lon):
        p = next((x["name"] for x in places if distance_m(lat, lon, x["lat"], x["lon"]) <= x["r"]), None)
        if p:
            return p
        g = geo.reverse(lat, lon, lang)
        return g["text"] if g else None

    # destination: the known place we are getting closer to (fallback: learned trip prediction)
    dest = None
    for p in places:
        d0 = distance_m(origin.lat, origin.lon, p["lat"], p["lon"])
        d1 = distance_m(cur.lat, cur.lon, p["lat"], p["lon"])
        if d1 > p["r"] and d0 - d1 > 150 and (dest is None or d1 < dest[1]):
            dest = (p, d1)
    st = trip_state(db, dev, now)
    if dest is None and st and st.get("trip"):
        p = next((x for x in places if x["name"] == st["trip"]["to"]), None)
        if p:
            dest = (p, distance_m(cur.lat, cur.lon, p["lat"], p["lon"]))
    out = {"started_at": hhmm(first.ts), "started_from": name_at(origin.lat, origin.lon),
           "minutes_travelling": round(mins), "km_so_far": round(km, 1), "speed_kmh": round(dev.last_speed or 0),
           "avg_speed_kmh": round(avg, 1)}
    if dest:
        p, d = dest
        road_km = d / 1000 * 1.3                                 # roads are ~30% longer than a straight line
        eta_min = max(1, round(road_km / speed * 60))
        out.update({"heading_to": p["name"], "km_left": round(road_km, 1), "eta_minutes": eta_min,
                    "eta_time": hhmm(now + timedelta(minutes=eta_min))})
    return out


def describe_location(db: Session, dev: Device, lang: str = "en") -> dict:
    """Human description of the last location: place name + distance/direction to known places (no lat/lon)."""
    from . import geo
    if dev.last_lat is None:
        return {}
    places = _known_places(db, dev)
    here = next((p["name"] for p in places if distance_m(dev.last_lat, dev.last_lon, p["lat"], p["lon"]) <= p["r"]), None)
    g = geo.reverse(dev.last_lat, dev.last_lon, lang)
    near = sorted(({"place": p["name"], "distance_m": int(distance_m(dev.last_lat, dev.last_lon, p["lat"], p["lon"])),
                    "direction_from_place": geo.bearing_word(p["lat"], p["lon"], dev.last_lat, dev.last_lon)}
                   for p in places), key=lambda x: x["distance_m"])[:3]
    return {"at_known_place": here, "location_name": g["text"] if g else None,
            "area": g["area"] if g else None, "city": g["city"] if g else None, "known_places_nearby": near}


def _since_at(db: Session, dev: Device, p: dict, now: datetime) -> datetime | None:
    """When did the child arrive at place p for the current stay? (walks back through the continuous stay)"""
    pts = db.scalars(select(Location).where(Location.device_pk == dev.id, Location.ts >= now - timedelta(hours=36),
                                            Location.ts <= now).order_by(Location.ts.desc())).all()
    since = None
    for x in pts:
        if distance_m(x.lat, x.lon, p["lat"], p["lon"]) > p["r"] + 30:
            break
        since = x.ts
    return since


def _mode(spd: float | None) -> str | None:
    if not spd or spd < 3:
        return None
    return "walking" if spd < 7 else "cycling" if spd < 15 else "vehicle"


def brief(db: Session, dev: Device, lang: str = "en", now: datetime | None = None) -> dict:
    """Everything a parent wants at a glance, computed from GPS (no AI, no guessing). Used by the family screen
    and by the assistant (current_status), so both always tell the same story."""
    from . import geo
    from . import places as P
    from .models import Bus
    from .services import active_sos
    now = now or datetime.now(timezone.utc)
    out: dict = {"name": dev.name or dev.device_id, "battery": dev.battery, "charging": bool(dev.charging)}
    sos = active_sos(db, dev)
    if sos:
        out.update(state="sos", sos_since=hhmm(sos.started_at))
    if dev.last_seen is None or dev.last_lat is None:
        out.setdefault("state", "never")
        return out
    mins_ago = int((now - as_utc(dev.last_seen)).total_seconds() // 60)
    online = mins_ago < settings.offline_after_minutes
    out.update(last_report=hhmm(dev.last_seen), minutes_ago=mins_ago, online=online,
               accuracy_m=int(dev.last_accuracy) if dev.last_accuracy else None)
    # only the parent's saved places by name – learned stops ("Frequent place 1") mean nothing to a parent
    places = [p for p in _known_places(db, dev) if p.get("saved")]
    here = next((p for p in places if distance_m(dev.last_lat, dev.last_lon, p["lat"], p["lon"]) <= p["r"]), None)
    today = local(now).date()
    model = get_model(db, dev)
    tm = json.loads(model.trips or "{}")
    sched = P.schedule_today(db, dev, today)
    now_hm = hhmm(now)

    trip = live_trip(db, dev, lang, now) if online and not here else None
    if here:
        out["place"] = here["name"]
        kind = next((g.kind for g in db.scalars(select(Geofence).where(Geofence.device_pk == dev.id)).all()
                     if g.name == here["name"]), None)
        out["place_kind"] = kind
        since = _since_at(db, dev, here, now)
        if since:
            out["since"] = hhmm(since)
            out["since_day"] = "yesterday" if local(since).date() < today else "today"
            # on time? the parent's schedule first, else the learned usual arrival
            slot = next((x for x in sched if x["place"] == here["name"] and x["start"] <= now_hm < x["end"]), None)
            usual = slot["start"] if slot else next(
                (t["usual_arrive"] for t in tm.get("trips", []) if t["to"] == here["name"] and _routine_today(tm, t, today)
                 and abs(_min_of(t["usual_arrive"]) - _min_of(hhmm(since))) <= 120), None)
            if usual and out["since_day"] == "today":
                late = _min_of(hhmm(since)) - _min_of(usual)
                out["usual_arrival"] = usual
                out["arrival"] = "late" if late > 10 else "early" if late < -20 else "on_time"
                out["late_min"] = max(0, late)
            if slot:
                out["until"] = slot["end"]
    else:
        g = geo.reverse(dev.last_lat, dev.last_lon, lang)
        out["near"] = g["text"] if g else None
        if places:
            p = min(places, key=lambda x: distance_m(dev.last_lat, dev.last_lon, x["lat"], x["lon"]))
            out["nearest_place"] = {"name": p["name"], "m": int(distance_m(dev.last_lat, dev.last_lon, p["lat"], p["lon"])),
                                    "direction": geo.bearing_word(p["lat"], p["lon"], dev.last_lat, dev.last_lon)}
    if trip:
        out["trip"] = {k: trip.get(k) for k in ("started_from", "started_at", "km_so_far", "minutes_travelling",
                                                "heading_to", "eta_time", "eta_minutes", "km_left")
                       if not (k == "km_so_far" and (trip.get(k) or 0) < 0.1)}         # "0 km so far" says nothing
        out["mode"] = _mode(dev.last_speed)
    out.setdefault("state", "offline" if not online else "at" if here else "moving" if trip else "stopped")

    # what comes next today: the parent's schedule first, else the learned routine
    nxt = next((x for x in sched if x["start"] > now_hm and x["place"] != (here or {}).get("name")), None)
    if nxt:
        out["next"] = {"place": nxt["place"], "at": nxt["start"], "source": "schedule"}
    else:
        st = trip_state(db, dev, now)
        t = st.get("next") if st and st.get("state") == "at" else None
        if t and not is_holiday(db, dev, today):
            out["next"] = {"place": t["to"], "leave": t["usual_depart"], "at": t["usual_arrive"], "source": "routine"}

    if dev.on_bus_id:
        bus = db.get(Bus, dev.on_bus_id)
        out["on_bus"] = bus.name if bus else None
    f = battery_forecast(db, dev, now)
    if f and f.get("empty_at"):
        out["battery_until"] = f["empty_at"]
    out["battery_low"] = (dev.battery or 100) <= 20 and not dev.charging
    day0 = datetime.combine(today, datetime.min.time(), tz()).astimezone(timezone.utc)
    al = db.scalars(select(AiAlert).where(AiAlert.device_pk == dev.id, AiAlert.ts >= day0,
                                          AiAlert.kind.notin_(["holiday_no", "weekly", "route_ok", "route_pause"]))
                    .order_by(AiAlert.ts.desc())).all()
    out["alerts_today"] = len(al)
    if al:
        out["last_alert"] = {"time": hhmm(al[0].ts), "kind": al[0].kind, "text": al[0].text}
    if route_paused(dev, now):
        out["route_alerts_paused_until"] = hhmm(dev.route_ok_until)
    if is_holiday(db, dev, today):
        out["holiday"] = True
    return out


# ---------------- routine alerts: late / did not leave / missed place ----------------
def _alerted_since(db: Session, dev: Device, kind: str, since: datetime, key: str) -> bool:
    return any(key in a.text for a in db.scalars(select(AiAlert).where(
        AiAlert.device_pk == dev.id, AiAlert.kind == kind, AiAlert.ts >= since)).all())


def _holiday_state(db: Session, dev: Device, day0: datetime) -> str:
    """'' / 'asked' (waiting for parent) / 'no' (parent said not a holiday)."""
    kinds = {a.kind: a for a in db.scalars(select(AiAlert).where(
        AiAlert.device_pk == dev.id, AiAlert.ts >= day0, AiAlert.kind.in_(["holiday_q", "holiday_no"]))).all()}
    if "holiday_no" in kinds:
        return "no"
    if "holiday_q" in kinds:
        asked = as_utc(kinds["holiday_q"].ts)
        return "asked" if datetime.now(timezone.utc) - asked < timedelta(minutes=45) else "no"   # no answer -> normal alerts
    return ""


def check_routine(db: Session, dev: Device, users: list[User], now: datetime | None = None) -> list[str]:
    """Called on each report and every minute by the monitor. Returns kinds alerted (for tests)."""
    now = now or datetime.now(timezone.utc)
    model = get_model(db, dev)
    if model.days < settings.ai_min_days or dev.last_lat is None:
        return []
    label = dev.name or dev.device_id
    tm = json.loads(model.trips or "{}")
    today = local(now).date()
    day0 = datetime.combine(today, datetime.min.time(), tz()).astimezone(timezone.utc)
    now_min = local(now).hour * 60 + local(now).minute
    st = trip_state(db, dev, now)
    fired = []
    holiday = is_holiday(db, dev, today)

    # ---- during a trip: detour from THIS trip's route, vehicle speed, lingering, late
    if st and st["state"] == "moving" and st.get("trip"):
        t = st["trip"]
        dep = st["departed"]
        path = set(t.get("path") or []) | extra_cells(model) if t.get("path") else set()   # no learned path -> no detour
        ci, cj = cell(dev.last_lat, dev.last_lon)
        on_path = any(_key((ci + a, cj + b)) in path for a in (-1, 0, 1) for b in (-1, 0, 1))
        dev.ai_detour = 0 if on_path or not path else (dev.ai_detour or 0) + 1
        key = f"{st['from']} → {t['to']} (left {hhmm(dep)})"
        if dev.ai_detour >= settings.ai_offroute_points and not _alerted_since(db, dev, "detour", dep, key) \
                and not _alerted_since(db, dev, "route", dep, ""):          # one alert per trip
            near = min((distance_m(dev.last_lat, dev.last_lon, int(k.split(":")[0]) * CELL, int(k.split(":")[1]) * CELL)
                        for k in path), default=0)
            _alert(db, dev, users, "detour", src=st["from"], dst=t["to"], left=hhmm(dep), near=int(near),
                   time=hhmm(now))
            fired.append("detour")
        usual_v = t.get("speed_p90")
        spd = dev.last_speed or 0
        if usual_v and spd > max(15, usual_v * 1.8) and not _alerted_since(db, dev, "speed", dep, key):
            mode = "walks" if (t.get("speed_med") or 0) < 7 else "cycles" if (t.get("speed_med") or 0) < 15 else "travels"
            _alert(db, dev, users, "speed", speed=int(spd), src=st["from"], dst=t["to"], left=hhmm(dep), mode=mode,
                   usual=int(t.get("speed_med") or 0))
            fired.append("speed")
        if dev.stop_since is not None and dev.stop_lat is not None and \
                distance_m(dev.stop_lat, dev.stop_lon, dev.last_lat, dev.last_lon) <= 80:
            mins = (now - as_utc(dev.stop_since)).total_seconds() / 60
            if mins >= 10 and as_utc(dev.stop_since) >= as_utc(dep) and \
                    place_name(db, dev, dev.last_lat, dev.last_lon, json.loads(model.places)) is None and \
                    not _alerted_since(db, dev, "linger", dep, key):
                _alert(db, dev, users, "linger", mins=int(mins), src=st["from"], dst=t["to"], left=hhmm(dep),
                       since=hhmm(dev.stop_since))
                fired.append("linger")

        # late arrival (routine alert – paused on holidays; scheduled places have their own "not there by" alert)
        limit = max(t["p80_min"] * 1.3, t["median_min"] + 15) if t.get("p80_min") else None
        took = (now - as_utc(dep)).total_seconds() / 60
        lkey = f"after leaving {st['from']} at {hhmm(dep)}"
        if not holiday and limit and not t.get("scheduled") and took > limit and \
                not _alerted_since(db, dev, "late", dep, lkey):
            d = distance_m(dev.last_lat, dev.last_lon, t["lat"], t["lon"])
            _alert(db, dev, users, "late", dst=t["to"], median=t["median_min"], src=st["from"], left=hhmm(dep),
                   time=hhmm(now), took=int(took), km=f"{d / 1000:.1f}")
            fired.append("late")

    if holiday:
        return fired

    hs = _holiday_state(db, dev, day0)
    if hs == "asked":
        return fired                      # waiting for the parent's answer (max 45 min)
    day_pts = db.scalars(select(Location).where(Location.device_pk == dev.id, Location.ts >= day0,
                                                Location.ts <= now)).all()
    moved_today = len(day_pts) > 1 and max(distance_m(day_pts[0].lat, day_pts[0].lon, p.lat, p.lon) for p in day_pts) > 300

    for t in tm.get("trips", []):
        if t["count"] < 3 or not _routine_today(tm, t, today):
            continue
        # 4) did not leave on time
        dep = _min_of(t["usual_depart"])
        tol = max(30, t.get("depart_spread", 0) + 15)
        if st and st["state"] == "at" and st["place"] == t["from"] and dep + tol < now_min < dep + 180:
            key = f"{t['from']} → {t['to']}"
            if not moved_today and hs == "":
                # gentle first question instead of alarms: maybe a holiday / sick day
                _alert(db, dev, users, "holiday_q", src=t["from"], usual=t["usual_depart"])
                fired.append("holiday_q")
                return fired
            if not _alerted_since(db, dev, "noleave", day0, key):
                _alert(db, dev, users, "noleave", src=t["from"], dst=t["to"], usual=t["usual_depart"], time=hhmm(now))
                fired.append("noleave")
        # 5) missed place
        arr = _min_of(t["usual_arrive"])
        if arr + 45 < now_min < arr + 360:
            pl = next((p for p in json.loads(model.places) if p["name"] == t["to"]), None) or _gf(db, dev, t["to"])
            if pl is None or (st and st["state"] == "at"):
                continue                  # at one of the child's places (e.g. Swimming instead of Home) -> safe
            if st and st["state"] == "moving" and st.get("trip") and st["trip"]["to"] == t["to"]:
                continue
            window = day0 + timedelta(minutes=max(0, arr - 120))
            seen = [p for p in day_pts if as_utc(p.ts) >= window]
            if not seen or any(distance_m(p.lat, p.lon, pl["lat"], pl["lon"]) <= 200 for p in seen):
                continue
            key = f"didn't reach {t['to']}"
            if not _alerted_since(db, dev, "missed", day0, key):
                _alert(db, dev, users, "missed", dst=t["to"], usual=t["usual_arrive"], last=hhmm(dev.last_seen))
                fired.append("missed")
    return fired


def answer_holiday(db: Session, dev: Device, user: User, is_holiday_: bool):
    today = datetime.now(tz()).date()
    if is_holiday_:
        set_holidays(db, dev, user, [today], "Answered: holiday")
    else:
        db.add(AiAlert(device_pk=dev.id, kind="holiday_no", text="Parent: not a holiday"))


def set_holidays(db: Session, dev: Device, user: User, days: list[date], note: str | None = None):
    have = holidays(db, dev)
    for d in days:
        if d.isoformat() not in have:
            db.add(Holiday(device_pk=dev.id, day=d.isoformat(), note=note, created_by=user.id))


def check_all_routines(db: Session) -> int:
    """Monitor loop (every minute): 'did not leave' / 'missed' need checks even when the tracker is quiet."""
    from .plans import allows
    from .services import device_users
    from .services_help import device_plan
    n = 0
    from . import places
    for dev in db.scalars(select(Device).where(Device.claimed.is_(True), Device.last_lat.is_not(None))).all():
        try:
            n += places.check_schedules(db, dev)      # "not at Swimming by 07:15" – every plan
        except Exception:
            log.exception("schedule check failed for %s", dev.device_id)
        try:
            if allows(device_plan(db, dev), "ai"):
                n += len(check_routine(db, dev, device_users(db, dev)))
                check_battery(db, dev, device_users(db, dev))
        except Exception:
            continue
    db.commit()
    send_weekly_reports(db)
    return n


# ---------------- day timeline + summary ----------------
def day_facts(db: Session, dev: Device, day: date) -> dict:
    start = datetime.combine(day, datetime.min.time(), tz()).astimezone(timezone.utc)
    end = start + timedelta(days=1)
    pts = db.scalars(select(Location).where(Location.device_pk == dev.id, Location.ts >= start, Location.ts < end)
                     .order_by(Location.ts)).all()
    places = json.loads(get_model(db, dev).places)
    stops = []
    for s in detect_stops(pts):
        stops.append({"place": place_name(db, dev, s["lat"], s["lon"], places) or "Unfamiliar place",
                      "from": hhmm(s["start"]), "to": hhmm(s["end"]), "minutes": s["minutes"],
                      "lat": round(s["lat"], 5), "lon": round(s["lon"], 5)})
    km = path_km(pts)
    alerts = db.scalars(select(AiAlert).where(AiAlert.device_pk == dev.id, AiAlert.ts >= start, AiAlert.ts < end)).all()
    sos = db.scalars(select(SosEvent).where(SosEvent.device_pk == dev.id, SosEvent.started_at >= start,
                                            SosEvent.started_at < end)).all()
    samples, last_h = [], None
    for p in pts:   # one sample per 15 min for the assistant
        k = (local(p.ts).hour, local(p.ts).minute // 15)
        if k != last_h:
            last_h = k
            samples.append({"time": hhmm(p.ts), "lat": round(p.lat, 5), "lon": round(p.lon, 5),
                            "place": place_name(db, dev, p.lat, p.lon, places)})
    return {"child": dev.name or dev.device_id, "date": day.isoformat(), "reports": len(pts),
            "first_report": hhmm(pts[0].ts) if pts else None, "last_report": hhmm(pts[-1].ts) if pts else None,
            "stops": stops, "distance_km": round(km, 1),
            "max_speed_kmh": round(max((p.speed or 0) for p in pts), 1) if pts else 0,
            "min_battery": min((p.battery for p in pts if p.battery is not None), default=None),
            "alerts": [{"time": hhmm(a.ts), "kind": a.kind, "text": a.text} for a in alerts],
            "sos": [{"time": hhmm(s.started_at), "status": s.status} for s in sos], "samples": samples}


def summary(db: Session, dev: Device, day: date) -> dict:
    f = day_facts(db, dev, day)
    if not f["reports"]:
        text = f"No location reports for {f['child']} on {day.strftime('%d %b')}."
    else:
        mood = "Normal day" if not f["alerts"] and not f["sos"] else \
            f"Attention: {len(f['sos'])} SOS, {len(f['alerts'])} unusual alert(s)"
        path = ", ".join(f"{s['place']} {s['from']}–{s['to']}" for s in f["stops"]) or "no long stops"
        text = f"{mood}. {path}. Travelled {f['distance_km']} km."
        if f["min_battery"] is not None and f["min_battery"] <= 20:
            text += f" Battery went down to {f['min_battery']}%."
    ai_text = llm.complete("Write a 2-sentence daily safety summary for the parent.", {k: v for k, v in f.items()
                                                                                       if k != "samples"}) \
        if f["reports"] else None
    return {"date": f["date"], "text": ai_text or text, "source": "ai" if ai_text else "data", "facts": f}


def day_list(db: Session, dev: Device, dates: list[date]) -> list[dict]:
    """One row per day (newest first) for the history list."""
    today = datetime.now(tz()).date()
    out = []
    for d in sorted(dates, reverse=True):
        k = (today - d).days
        f = day_facts(db, dev, d)
        if not f["reports"]:
            status, line = "nodata", "No reports"
        elif f["sos"] or f["alerts"]:
            status = "attention"
            line = " · ".join(x for x in [f"{len(f['sos'])} SOS" if f["sos"] else "",
                                         f"{len(f['alerts'])} alert(s)" if f["alerts"] else ""] if x)
        else:
            status, line = "normal", "Normal day"
        places = []
        for st in f["stops"]:
            if st["place"] not in places:
                places.append(st["place"])
        out.append({"date": d.isoformat(), "label": "Today" if k == 0 else "Yesterday" if k == 1 else d.strftime("%a, %d %b"),
                    "status": status, "line": line, "km": f["distance_km"], "places": places[:4],
                    "first": f["first_report"], "last": f["last_report"]})
    return out


def day_detail(db: Session, dev: Device, day: date) -> dict:
    """Full history of one day: timeline (stays, travel, alerts, SOS) + path for the map."""
    f = day_facts(db, dev, day)
    start = datetime.combine(day, datetime.min.time(), tz()).astimezone(timezone.utc)
    pts = db.scalars(select(Location).where(Location.device_pk == dev.id, Location.ts >= start,
                                            Location.ts < start + timedelta(days=1)).order_by(Location.ts)).all()
    items = []
    stops = f["stops"]
    for i, st in enumerate(stops):
        items.append({"time": st["from"], "kind": "stay", "title": st["place"],
                      "text": f"{st['from']}–{st['to']} · {st['minutes']} min"})
        if i + 1 < len(stops):
            nx = stops[i + 1]
            seg = [p for p in pts if st["to"] <= hhmm(p.ts) <= nx["from"]]
            km = path_km(seg)
            mins = _min_of(nx["from"]) - _min_of(st["to"])
            items.append({"time": st["to"], "kind": "travel", "title": f"{st['place']} → {nx['place']}",
                          "text": f"{st['to']}–{nx['from']} · {mins} min · {km:.1f} km"})
    for a in f["alerts"]:
        items.append({"time": a["time"], "kind": "alert", "title": "Unusual activity", "text": a["text"]})
    for x in f["sos"]:
        items.append({"time": x["time"], "kind": "sos", "title": "SOS pressed", "text": f"Status: {x['status']}"})
    from .models import Bus, BusEvent
    for e in db.scalars(select(BusEvent).where(BusEvent.device_pk == dev.id, BusEvent.ts >= start,
                                               BusEvent.ts < start + timedelta(days=1))).all():
        b = db.get(Bus, e.bus_id)
        items.append({"time": hhmm(e.ts), "kind": "bus", "title": ("Boarded " if e.kind == "board" else "Got off ") +
                      (b.name if b else "bus"), "text": place_name(db, dev, e.lat, e.lon) or "" if e.lat else ""})
    if pts and not stops:
        items.append({"time": f["first_report"], "kind": "travel", "title": "On the move",
                      "text": f"{f['first_report']}–{f['last_report']} · no long stops"})
    items.sort(key=lambda x: x["time"] or "")
    step = max(1, len(pts) // 400)
    return {"date": day.isoformat(), "summary": summary(db, dev, day)["text"], "distance_km": f["distance_km"],
            "max_speed_kmh": f["max_speed_kmh"], "min_battery": f["min_battery"], "reports": f["reports"],
            "first": f["first_report"], "last": f["last_report"], "timeline": items,
            "path": [{"lat": p.lat, "lon": p.lon} for p in pts[::step]]}


def routine(db: Session, dev: Device) -> dict:
    m = get_model(db, dev)
    return {"days": m.days, "min_days": settings.ai_min_days, "places": json.loads(m.places),
            "trips": json.loads(m.trips or "{}").get("trips", [])}


# ---------------- battery prediction ----------------
def battery_forecast(db: Session, dev: Device, now: datetime | None = None) -> dict | None:
    """Linear fit of the last 6 h of battery readings while not charging -> when it will reach 0 %."""
    now = now or datetime.now(timezone.utc)
    if dev.battery is None or dev.charging:
        return None
    pts = [p for p in db.scalars(select(Location).where(Location.device_pk == dev.id, Location.ts >= now - timedelta(hours=6),
                                                        Location.battery.is_not(None)).order_by(Location.ts)).all()]
    if len(pts) < 3:
        return None
    t0 = as_utc(pts[0].ts)
    xs = [(as_utc(p.ts) - t0).total_seconds() / 3600 for p in pts]
    ys = [p.battery for p in pts]
    if xs[-1] - xs[0] < 0.5:
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    den = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den if den else 0      # % per hour
    if slope >= -0.2:
        return {"battery": dev.battery, "per_hour": round(-slope, 1), "hours_left": None, "text": f"Battery {dev.battery}% – steady"}
    hours = dev.battery / -slope
    empty = now + timedelta(hours=hours)
    return {"battery": dev.battery, "per_hour": round(-slope, 1), "hours_left": round(hours, 1), "empty_at": hhmm(empty),
            "text": f"Battery {dev.battery}% – will run out around {hhmm(empty)}"
                    + (" tomorrow" if local(empty).date() != local(now).date() else "") + f" (~{hours:.0f} h)"}


def check_battery(db: Session, dev: Device, users: list[User], now: datetime | None = None) -> bool:
    """Warn once a day if the tracker will die within 3 h and is still above the 15 % low-battery alert."""
    now = now or datetime.now(timezone.utc)
    f = battery_forecast(db, dev, now)
    today = local(now).date().isoformat()
    if not f or f.get("hours_left") is None or f["hours_left"] > 3 or (dev.battery or 0) <= settings.low_battery_percent \
            or dev.battery_warned_on == today:
        return False
    dev.battery_warned_on = today
    label = dev.name or dev.device_id
    _alert(db, dev, users, "battery", label=label, bat=dev.battery, empty_at=f["empty_at"])
    return True


# ---------------- weekly report ----------------
def weekly_report(db: Session, dev: Device, week_start: date | None = None) -> dict:
    """Mon–Sun report: days with data, places, punctuality, alerts, SOS, distance, battery."""
    today = datetime.now(tz()).date()
    ws = week_start or (today - timedelta(days=today.weekday()))
    days = [ws + timedelta(days=k) for k in range(7) if ws + timedelta(days=k) <= today]
    label = dev.name or dev.device_id
    facts = [day_facts(db, dev, d) for d in days]
    with_data = [f for f in facts if f["reports"]]
    km = round(sum(f["distance_km"] for f in facts), 1)
    alerts = [a for f in facts for a in f["alerts"]]
    sos = [s_ for f in facts for s_ in f["sos"]]
    tm = json.loads(get_model(db, dev).trips or "{}")
    punct = []
    for t in tm.get("trips", []):
        if t["count"] < 3:
            continue
        um = _min_of(t["usual_arrive"])
        arr = []
        for d, f in zip(days, facts):
            st = next((x for x in f["stops"] if x["place"] == t["to"]), None)
            if st:
                arr.append((d, _min_of(st["from"])))
        if arr:
            late = [d for d, m in arr if m > um + 10]
            punct.append({"trip": f"{t['from']} → {t['to']}", "usual": t["usual_arrive"], "days": len(arr),
                          "late_days": len(late), "late_on": [d.strftime("%a") for d in late]})
    places: dict[str, int] = {}
    for f in facts:
        for p_ in {x["place"] for x in f["stops"]}:
            places[p_] = places.get(p_, 0) + 1
    low_bat = min((f["min_battery"] for f in facts if f["min_battery"] is not None), default=None)
    lines = [f"Week of {ws.strftime('%d %b')}: {len(with_data)} day(s) with tracker data, {km} km travelled."]
    lines.append(f"{len(sos)} SOS, {len(alerts)} unusual alert(s)." if (sos or alerts) else "No SOS and no unusual alerts ✅.")
    for p_ in punct:
        lines.append(f"{p_['trip']}: on time {p_['days'] - p_['late_days']}/{p_['days']}" +
                     (f" (late {', '.join(p_['late_on'])})" if p_["late_days"] else "") + ".")
    if low_bat is not None and low_bat <= 20:
        lines.append(f"Battery went down to {low_bat}% – charge every night.")
    return {"week_start": ws.isoformat(), "days_with_data": len(with_data), "km": km, "sos": len(sos),
            "alerts": len(alerts), "punctuality": punct, "places": places, "min_battery": low_bat,
            "text": " ".join(lines), "child": label}


def send_weekly_reports(db: Session, now: datetime | None = None) -> int:
    """Sunday 19:00 IST: push the weekly report to the family (once per week)."""
    from .plans import allows
    from .services import device_users
    from .services_help import device_plan
    now = now or datetime.now(timezone.utc)
    ln = local(now)
    if ln.weekday() != 6 or ln.hour < 19:
        return 0
    week0 = ln.date() - timedelta(days=6)
    start = datetime.combine(week0, datetime.min.time(), tz()).astimezone(timezone.utc)
    n = 0
    for dev in db.scalars(select(Device).where(Device.claimed.is_(True))).all():
        if not allows(device_plan(db, dev), "ai"):
            continue
        if db.scalar(select(AiAlert).where(AiAlert.device_pk == dev.id, AiAlert.kind == "weekly", AiAlert.ts >= start)):
            continue
        r = weekly_report(db, dev, week0)
        db.add(AiAlert(device_pk=dev.id, kind="weekly", text=r["text"][:300],
                       msg_args=push_msgs.args_json(label=r["child"], text=r["text"][:300])))
        push_msgs.push(device_users(db, dev), "weekly", {"type": "ai_alert", "kind": "weekly", "device_id": dev.device_id,
                                                         "text": r["text"][:300]}, label=r["child"], text=r["text"][:200])
        n += 1
    db.commit()
    return n


# ---------------- assistant ----------------
_TIME = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b|\b(\d{1,2}):(\d{2})\b", re.I)


def _known_places(db: Session, dev: Device) -> list[dict]:
    out = [{"name": g.name, "lat": g.lat, "lon": g.lon, "r": g.radius_m + 75, "saved": True}
           for g in db.scalars(select(Geofence).where(Geofence.device_pk == dev.id)).all()]
    for p in json.loads(get_model(db, dev).places):
        if all(p["name"] != o["name"] for o in out):
            out.append({"name": p["name"], "lat": p["lat"], "lon": p["lon"], "r": 200})
    return out


_ALIASES = {"home": ["home", "house", "ghar"], "school": ["school", "class"], "tuition": ["tuition", "coaching"]}


def _match_place(places: list[dict], q: str) -> dict | None:
    words = set(re.findall(r"[a-z]{3,}", q))
    for p in places:
        n = p["name"].lower()
        if n in q or any(w in words for w in re.findall(r"[a-z]{4,}", n)):
            return p
        for key, al in _ALIASES.items():
            if key in n and words & set(al):
                return p
    return None


def _ago(dt: datetime) -> str:
    m = int((datetime.now(timezone.utc) - as_utc(dt)).total_seconds() // 60)
    return f"{m} min ago" if m < 120 else f"{m // 60} h ago"


def expected_place(db: Session, dev: Device, when: datetime | None = None) -> dict | None:
    """From the learned routine: where is the child USUALLY at this time on this weekday?"""
    when = when or datetime.now(timezone.utc)
    model = get_model(db, dev)
    if model.days < 3:
        return None
    tm = json.loads(model.trips or "{}")
    day = local(when).date()
    if is_holiday(db, dev, day):
        return {"place": None, "holiday": True}
    m = local(when).hour * 60 + local(when).minute
    trips = sorted([t for t in tm.get("trips", []) if _routine_today(tm, t, day)], key=lambda t: _min_of(t["usual_depart"]))
    if not trips:
        return None
    for t in trips:
        dep, arr = _min_of(t["usual_depart"]), _min_of(t["usual_arrive"])
        if dep <= m < arr:
            return {"place": None, "travelling": t, "since": t["usual_depart"]}
    done = [t for t in trips if _min_of(t["usual_arrive"]) <= m]
    if done:
        t = done[-1]
        nxt = next((x for x in trips if _min_of(x["usual_depart"]) > m), None)
        return {"place": t["to"], "since": t["usual_arrive"], "next": nxt}
    t = trips[0]
    return {"place": t["from"], "since": None, "next": t}


def _usual_text(e: dict | None, label: str) -> str:
    if not e:
        return ""
    if e.get("holiday"):
        return f"Today is marked as a holiday for {label}."
    if e.get("travelling"):
        t = e["travelling"]
        return f"By routine, at this time {label} is usually on the way {t['from']} → {t['to']} (arrives ~{t['usual_arrive']})."
    txt = f"By routine, at this time {label} is usually at {e['place']}" + (f" (from ~{e['since']})" if e.get("since") else "")
    if e.get("next"):
        txt += f", leaving for {e['next']['to']} ~{e['next']['usual_depart']}"
    return txt + "."


def _status(db: Session, dev: Device, places: list[dict]) -> str:
    from .services import active_sos
    label = dev.name or dev.device_id
    if dev.last_seen is None:
        return f"No report from {label}'s tracker yet."
    here = next((p["name"] for p in places if dev.last_lat is not None and
                 distance_m(dev.last_lat, dev.last_lon, p["lat"], p["lon"]) <= p["r"]), None)
    where = f"at {here}" if here else "at a place not in the routine"
    if not here:
        from . import geo
        g = geo.reverse(dev.last_lat, dev.last_lon) if dev.last_lat is not None else None
        if g:
            where = f"near {g['text']}"
    sos = active_sos(db, dev)
    head = f"🚨 SOS is ACTIVE since {hhmm(sos.started_at)} – open the SOS screen. " if sos else ""
    online = as_utc(dev.last_seen) > datetime.now(timezone.utc) - timedelta(minutes=settings.offline_after_minutes)
    bat = f"battery {dev.battery if dev.battery is not None else '–'}%"
    exp = expected_place(db, dev)
    usual = _usual_text(exp, label)
    if not online:
        why = "The battery was low – it has probably run out. " if (dev.battery or 100) <= 20 else ""
        return (head + f"⚠️ The tracker is OFFLINE – no update for {_ago(dev.last_seen).replace(' ago', '')}, so this is "
                f"not live. Last known: {where} at {hhmm(dev.last_seen)}, {bat}. {why}"
                + (usual + " (estimate, not a live location) " if usual else "")
                + "Please call or check the tracker is charged and switched on.")
    match = ""
    if exp and exp.get("place") and here:
        match = f" ✅ That's where {label} usually is at this time." if exp["place"] == here else \
            f" Note: usually {label} is at {exp['place']} at this time."
    fresh = "just now" if _ago(dev.last_seen).startswith(("0 ", "1 ")) else _ago(dev.last_seen)
    moving = (dev.last_speed or 0) >= (8 if here else 3)     # small speeds inside a place = GPS jitter
    trip = live_trip(db, dev) if moving else None
    trip_txt = ""
    if trip:
        trip_txt = f"\n🚶 Left {trip['started_from'] or 'the last stop'} at {trip['started_at']} · {trip['km_so_far']} km so far"
        if trip.get("heading_to"):
            trip_txt += f" · heading to {trip['heading_to']}, expected ~{trip['eta_time']} ({trip['eta_minutes']} min)"
        trip_txt += "."
    return (f"📍 {label} is {where}" + (f", moving at {int(dev.last_speed)} km/h" if moving else "") +
            f" (updated {hhmm(dev.last_seen)}, {fresh}).{match}{trip_txt}\n🔋 {bat.capitalize()} · "
            + ("🚨 SOS ACTIVE – open the SOS screen." if sos else "✅ No SOS."))


def _eta_answer(db: Session, dev: Device, label: str, dest: dict | None, places: list[dict]) -> str:
    """'When will he come home?' – live ETA if travelling, else the routine's next trip."""
    if dest is None:
        return (f"I don't know where Home is yet. Add a “Home” safe zone on the map (🏠) and I'll tell you when "
                f"{label} usually reaches it.")
    if dev.last_lat is None or dev.last_seen is None:
        return f"No location from {label}'s tracker yet."
    online = as_utc(dev.last_seen) > datetime.now(timezone.utc) - timedelta(minutes=settings.offline_after_minutes)
    d = distance_m(dev.last_lat, dev.last_lon, dest["lat"], dest["lon"])
    if online and d <= dest["r"]:
        return f"🏠 {label} is already at {dest['name']} (updated {hhmm(dev.last_seen)})."
    here = next((p["name"] for p in places if distance_m(dev.last_lat, dev.last_lon, p["lat"], p["lon"]) <= p["r"]), None)
    e = eta(db, dev)
    if online and e and e.get("state") == "moving" and e.get("to") == dest["name"]:
        return (f"🚶 {label} is on the way to {dest['name']}. Expected at {e['arrive_at']} (about {e['minutes']} min, "
                f"{d / 1000:.1f} km left). Usually this trip takes {e['usual_min']} min.")
    # routine: next trip that ends at dest
    tm = json.loads(get_model(db, dev).trips or "{}")
    today = datetime.now(tz()).date()
    m = local(datetime.now(timezone.utc)).hour * 60 + local(datetime.now(timezone.utc)).minute
    trips = [t for t in tm.get("trips", []) if t["to"] == dest["name"] and _routine_today(tm, t, today)]
    t = next((x for x in sorted(trips, key=lambda x: _min_of(x["usual_depart"]))
              if (here is None or x["from"] == here) and _min_of(x["usual_arrive"]) >= m - 30), None)
    where = f"at {here}" if here else f"{d / 1000:.1f} km from {dest['name']}"
    status = f"{label} is {where} now" if online else f"Tracker offline – last seen {where} at {hhmm(dev.last_seen)}"
    if t:
        return (f"{status}. On a normal day {label} leaves {t['from']} ~{t['usual_depart']} and reaches "
                f"{dest['name']} ~{t['usual_arrive']} (about {t['median_min']} min). I'll update the time once "
                f"{label} starts moving.")
    live = _live_minutes(db, dev, d) if online else None
    if live:
        return f"{status}, moving. At the current speed {label} could reach {dest['name']} in about {live} min."
    return (f"{status} and not moving yet. I can't predict the time yet – I need about "
            f"{settings.ai_min_days} days of trips to learn when {label} usually comes to {dest['name']}.")


def ask(db: Session, dev: Device, question: str, use_llm: bool = True) -> dict:
    q = question.lower()
    today = datetime.now(tz()).date()
    day = today - timedelta(days=1) if "yesterday" in q else today
    dname = "yesterday" if day != today else "today"
    f = day_facts(db, dev, day)
    label = f["child"]
    places = _known_places(db, dev)
    answer = None
    day0 = datetime.combine(day, datetime.min.time(), tz()).astimezone(timezone.utc)
    pts = db.scalars(select(Location).where(Location.device_pk == dev.id, Location.ts >= day0,
                                            Location.ts < day0 + timedelta(days=1)).order_by(Location.ts)).all()
    place = _match_place(places, q)

    m = _TIME.search(q)
    if m:                                              # "where was he at 4 pm"
        if m.group(1):
            h, mi = int(m.group(1)) % 12 + (12 if m.group(3).lower() == "pm" else 0), int(m.group(2) or 0)
        else:
            h, mi = int(m.group(4)), int(m.group(5))
        want = datetime.combine(day, datetime.min.time(), tz()).replace(hour=h % 24, minute=mi).astimezone(timezone.utc)
        near = [p for p in pts if abs((as_utc(p.ts) - want).total_seconds()) <= 1200]
        if not near:
            first, last = (hhmm(pts[0].ts), hhmm(pts[-1].ts)) if pts else (None, None)
            answer = f"No location report for {label} around {h:02d}:{mi:02d} {dname}." +                 (f" Reports {dname} are from {first} to {last} (IST)." if pts else "")
        else:
            p = min(near, key=lambda x: abs((as_utc(x.ts) - want).total_seconds()))
            name = next((x["name"] for x in places if distance_m(p.lat, p.lon, x["lat"], x["lon"]) <= x["r"]), None)
            answer = f"At {hhmm(p.ts)} {label} was " + (f"at {name}." if name else f"near {p.lat:.5f}, {p.lon:.5f} (not a usual place).")
    elif any(w in q for w in ("when will", "when is", "how long", "eta", "coming", "come home", "will he", "will she",
                                "be home", "reach home", "get home", "arrive")) and day == today:
        answer = _eta_answer(db, dev, label, place or _match_place(places, q + " home"), places)
    elif any(w in q for w in ("safe", "okay", " ok", "fine", "status", "alright", "all good")):
        answer = _status(db, dev, places)
    elif place and any(w in q for w in ("reach", "arriv", "go to", "went", "get to", "come", "at ")):
        visits = [p for p in pts if distance_m(p.lat, p.lon, place["lat"], place["lon"]) <= place["r"]]
        now_there = dev.last_lat is not None and day == today and \
            distance_m(dev.last_lat, dev.last_lon, place["lat"], place["lon"]) <= place["r"]
        if now_there:
            answer = f"Yes – {label} is at {place['name']} now (first report there {dname} {hhmm(visits[0].ts) if visits else hhmm(dev.last_seen)})."
        elif visits:
            answer = f"Yes – {label} was at {place['name']} {dname} from {hhmm(visits[0].ts)} to {hhmm(visits[-1].ts)}. " \
                     f"Last report {hhmm(dev.last_seen)}."
        else:
            answer = f"No – {label} has not been at {place['name']} {dname}." + \
                (f" Last report {hhmm(pts[-1].ts)}." if pts else f" No reports {dname}.")
    elif place and any(w in q for w in ("leave", "left", "depart")):
        visits = [p for p in pts if distance_m(p.lat, p.lon, place["lat"], place["lon"]) <= place["r"]]
        if not visits:
            answer = f"{label} was not at {place['name']} {dname}."
        elif dev.last_lat is not None and distance_m(dev.last_lat, dev.last_lon, place["lat"], place["lon"]) <= place["r"]:
            answer = f"{label} has not left {place['name']} yet (there since {hhmm(visits[0].ts)})."
        else:
            answer = f"{label} left {place['name']} at about {hhmm(visits[-1].ts)}."
    elif "batter" in q or "charge" in q:
        answer = f"Battery {dev.battery if dev.battery is not None else '–'}%" + (" (charging)" if dev.charging else "") + \
            (f", last report {hhmm(dev.last_seen)}." if dev.last_seen else ".")
    elif any(w in q for w in ("how far", "distance", "km", "travel")):
        answer = f"{label} travelled {f['distance_km']} km {dname}."
    elif any(w in q for w in ("where", "location", "now")):
        answer = _status(db, dev, places)
    elif any(w in q for w in ("summary", "day", "today", "yesterday")):
        answer = summary(db, dev, day)["text"]

    ai = None if not use_llm else llm.complete(f"Parent asks: {question}", {**f, "current": {
        "time": hhmm(dev.last_seen) if dev.last_seen else None, "lat": dev.last_lat, "lon": dev.last_lon,
        "battery": dev.battery}, "known_places": [p["name"] for p in places]})
    if ai:
        return {"answer": ai, "source": "ai"}
    return {"answer": answer or (f"Sorry, I didn't understand that. I can tell you about {label} from the tracker – try: "
                                 f"“Where is {label} now?”, “When will {label} come home?”, “Did {label} reach school?”, "
                                 f"“Where was {label} at 4 pm?”, “Battery?”"), "source": "data"}


# ---------------- incident report (Guardian) ----------------
def incident_report(db: Session, sos: SosEvent) -> dict:
    dev = db.get(Device, sos.device_pk)
    label = dev.name or dev.device_id
    t0 = as_utc(sos.started_at)
    t1 = as_utc(sos.resolved_at) if getattr(sos, "resolved_at", None) else datetime.now(timezone.utc)
    ev = [(t0, f"SOS started ({'button on tracker' if sos.source == 'device' else 'parent emergency'})")]
    if getattr(sos, "acknowledged_at", None):
        u = db.get(User, sos.acknowledged_by) if sos.acknowledged_by else None
        ev.append((as_utc(sos.acknowledged_at), f"Acknowledged by {u.name if u else 'family'}"))
    if sos.school_notified_at:
        ev.append((as_utc(sos.school_notified_at), "School alerted"))
    for hr in db.scalars(select(HelpRequest).where(HelpRequest.sos_id == sos.id)).all():
        ev.append((as_utc(hr.created_at), f"Emergency – Group started ({hr.radius_m} m)"))
        if hr.expanded_at:
            ev.append((as_utc(hr.expanded_at), "Group radius widened"))
        for r in db.scalars(select(HelperResponse).where(HelperResponse.help_id == hr.id,
                                                         HelperResponse.status == "accepted")).all():
            u = db.get(User, r.user_id)
            ev.append((as_utc(r.accepted_at or hr.created_at), f"Helper {u.name if u else r.user_id} accepted"))
    views = db.scalars(select(LocationAccessLog).where(LocationAccessLog.sos_id == sos.id)).all()
    if sos.status in ("resolved", "cancelled"):
        ev.append((t1, f"SOS {sos.status}"))
    ev.sort(key=lambda x: x[0])
    pts = db.scalars(select(Location).where(Location.device_pk == dev.id, Location.ts >= t0 - timedelta(minutes=10),
                                            Location.ts <= t1).order_by(Location.ts)).all()
    km = path_km(pts)
    lines = [f"SelfXTrack incident report – {label}",
             f"Date: {local(t0).strftime('%d %b %Y')} · SOS #{sos.id} · status {sos.status}",
             f"Start location: {sos.lat:.5f}, {sos.lon:.5f}" if sos.lat is not None else "Start location: unknown",
             f"Last known: {pts[-1].lat:.5f}, {pts[-1].lon:.5f} at {hhmm(pts[-1].ts)}" if pts else "",
             f"Movement during incident: {km:.2f} km, {len(pts)} reports", "", "Timeline (IST):"]
    lines += [f"  {hhmm(t)}  {txt}" for t, txt in ev]
    lines += ["", f"Location viewed {len(views)} time(s) by school/helpers (access log kept).",
              "Generated automatically from tracker data."]
    return {"sos_id": sos.id, "text": "\n".join(x for x in lines if x is not None),
            "timeline": [{"time": hhmm(t), "event": txt} for t, txt in ev],
            "path": [{"time": hhmm(p.ts), "lat": p.lat, "lon": p.lon} for p in pts]}
