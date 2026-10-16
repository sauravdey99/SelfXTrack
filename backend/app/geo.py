"""Place names for a location (reverse geocoding), so answers say "near Sampangi Rama Nagar" instead of lat/lon.

Uses OpenStreetMap Nominatim (free; usage policy: max 1 request/second, real User-Agent, cache results).
For production volume run your own Nominatim or switch to a paid API (MapmyIndia, Google) – only reverse() changes.
SELFX_GEOCODER=none turns it off (tests). Failures return None and callers fall back to distances.
"""
import logging
import math
import re
import threading
import time

import httpx

from .config import settings

log = logging.getLogger("selfx.geo")
_cache: dict[tuple, dict | None] = {}
_lock = threading.Lock()
_last_call = 0.0
_LATIN = re.compile(r"^[\x00-ɏ\s\d.,'()&/-]+$")


def _pick(*vals):
    return next((v for v in vals if v), None)


def reverse(lat: float, lon: float, lang: str = "en") -> dict | None:
    """{"road", "area", "city", "text"} for a point, cached per ~50 m and language."""
    if settings.geocoder == "none" or lat is None or lon is None:
        return None
    key = (round(lat * 2000) / 2000, round(lon * 2000) / 2000, lang)       # ~50 m grid
    if key in _cache:
        return _cache[key]
    global _last_call
    with _lock:
        wait = 1.0 - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()
    out = None
    try:
        r = httpx.get("https://nominatim.openstreetmap.org/reverse", timeout=4,
                      params={"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 17, "addressdetails": 1,
                              "accept-language": f"{lang},en"},
                      headers={"User-Agent": "SelfXTrack/0.6 (child safety tracker; contact: admin@selfxtrack.in)"})
        r.raise_for_status()
        a = r.json().get("address") or {}
        road = a.get("road")
        area = _pick(a.get("neighbourhood"), a.get("suburb"), a.get("quarter"), a.get("village"), a.get("town"))
        city = _pick(a.get("city"), a.get("town"), a.get("county"))
        landmark = _pick(a.get("amenity"), a.get("school"), a.get("building"), a.get("shop"))
        if lang == "en" and road and not _LATIN.match(road):
            road = None                      # local-script road name only – the area name reads better in English
        parts = [p for p in (landmark, road, area) if p]
        text = ", ".join(dict.fromkeys(parts)) or city
        out = {"road": road, "area": area, "city": city, "landmark": landmark, "text": text} if text else None
    except Exception as e:                    # offline / rate limited – answers still work with distances
        log.warning("reverse geocode failed: %s", e)
        return None
    _cache[key] = out
    return out


def bearing_word(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """Compass direction from point 1 to point 2: north, north-east, …"""
    y = math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2))
    x = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - \
        math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(math.radians(lon2 - lon1))
    deg = (math.degrees(math.atan2(y, x)) + 360) % 360
    return ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"][round(deg / 45) % 8]
