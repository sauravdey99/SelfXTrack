"""Server-written alert texts (AI alerts, bus, inactivity, weekly) in every app language.

Most pushes (SOS, offline, geofence, battery …) are built on the phone from `type` + data and are already in the
app language. These alerts carry a sentence written here, so each recipient gets it in their own language
(User.lang, set from the app's language setting). English below must stay identical to the old texts:
_alerted_since() de-duplicates on substrings of the stored English text.

Translations live in push_msgs_tr.py; a missing language or key falls back to English.
"""
import json

from .models import User

# key -> (title, body). Placeholders use str.format names.
EN: dict[str, tuple[str, str]] = {
    "risk": ("⚠️ Check on {label}?",
             "{label} is moving fast ({speed} km/h) away from usual routes at {time}. About {near} m from usual places. "
             "Call to check – this is not an SOS."),
    "route": ("🧭 {label}: unusual route",
              "{label} is on a route not seen before – about {near} m from usual routes ({time})."),
    "time": ("🌙 {label}: usual road, unusual time",
             "{label} is on a road normally used around {h1}:00–{h2}:59, but it's {time}."),
    "stop": ("📍 {label} stopped at an unfamiliar place",
             "{label} has been at a place not visited before for {mins} min (since {since})."),
    "detour": ("↪️ {label} left the usual route",
               "{label} is not on the usual {src} → {dst} (left {left}) route – about {near} m away ({time})."),
    "speed": ("🚗 {label} is moving fast",
              "{label} is moving at {speed} km/h on {src} → {dst} (left {left}). Usually {mode} this trip (~{usual} km/h)."),
    "linger": ("⏸ {label} stopped on the way",
               "{label} has been stopped for {mins} min on {src} → {dst} (left {left}) since {since}."),
    "late": ("⏰ {label} is late for {dst}",
             "{label} usually reaches {dst} in {median} min after leaving {src} at {left}. "
             "It's {time} ({took} min) and {label} is still {km} km away."),
    "holiday_q": ("🏖 Holiday for {label} today?",
                  "{label} is still at {src} (usually leaves ~{usual}). Holiday today? "
                  "Open the app to answer – routine alerts wait 45 min."),
    "noleave": ("🕒 {label} hasn't left {src}",
                "{label} usually leaves {src} ~{usual} ({src} → {dst}). It's {time} and {label} is still there."),
    "missed": ("❓ {label} didn't reach {dst} today",
               "{label} didn't reach {dst} today (usually arrives ~{usual}). Last report {last}."),
    "battery": ("🔋 {label}'s tracker will run out soon",
                "{label}'s tracker battery ({bat}%) will run out around {empty_at}. Please charge it tonight."),
    "inactivity": ("🧓 Check on {label}",
                   "No movement from {label} for {hrs} h (since {since}). Please call to check."),
    "bus_on": ("🚌 {label} is on the bus", "{label} boarded {bus} at {time}."),
    "bus_on_near": ("🚌 {label} is on the bus", "{label} boarded {bus} at {time} near {place}."),
    "bus_off": ("🚌 {label} got off the bus", "{label} got off {bus} at {time}."),
    "bus_off_near": ("🚌 {label} got off the bus", "{label} got off {bus} at {time} near {place}."),
    "sched_late": ("⏰ {label} is not at {place} yet",
                   "{label} should be at {place} from {start}, but is not there yet ({time})."),
    "sched_early": ("🚶 {label} left {place} early", "{label} left {place} at {time} – it ends at {end}."),
    "route_ok": ("✅ {label}'s trip marked OK", "{by} marked {label}'s trip as OK – route alerts paused until {until}."),
    "route_pause": ("⏸ Route alerts paused", "{by} paused route alerts for {label} until {until}."),
    # English body = the report itself (passed as {text}); other languages get a short "report is ready" line
    "weekly": ("📊 {label}'s week", "{text}"),
}


def _tr() -> dict:
    from .push_msgs_tr import TR
    return TR


def render(key: str, lang: str | None, **p) -> tuple[str, str]:
    """(title, body) for one language; falls back to English for missing languages, keys or bad templates."""
    en = EN[key]
    tr = _tr().get(lang or "en", {}).get(key) if lang and lang != "en" else None
    for title, body in ([tr] if tr else []) + [en]:
        try:
            return title.format(**p), body.format(**p)
        except (KeyError, IndexError, ValueError):
            continue
    return en


def push(users: list[User], key: str, data: dict, **p) -> tuple[str, str]:
    """Send one alert to each user in their own language. data['text'] is replaced by the localized body
    (the phone shows it). Returns the English (title, body) for storing."""
    from . import notify
    by_lang: dict[str, list[User]] = {}
    for u in users:
        if u is not None:
            by_lang.setdefault(getattr(u, "lang", None) or "en", []).append(u)
    for lang, group in by_lang.items():
        title, body = render(key, lang, **p)
        notify.push(group, title, body, {**data, **({"text": body} if "text" in data else {})})
    return render(key, "en", **p)


def args_json(**p) -> str:
    return json.dumps({k: str(v) for k, v in p.items()}, ensure_ascii=False)


def alert_text(kind: str, stored_text: str, msg_args: str | None, lang: str | None) -> str:
    """Text of a saved AiAlert for the reader's language (old alerts without args stay as stored)."""
    if not msg_args or not lang or lang == "en":
        return stored_text
    try:
        p = json.loads(msg_args)
        key = p.pop("_key", kind)
        return render(key, lang, **p)[1] if key in EN else stored_text
    except (ValueError, TypeError):
        return stored_text
