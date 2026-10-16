"""Languages for the "Ask about <child>" assistant: English + 12 Indian languages.

- LLM engines get the language in the system prompt and answer in it directly (all languages).
- The rule-based parts (guardrails + local planner) only understand English/Hinglish keywords, so
  `keywords()` maps question words of every language to those keywords first (incl. emergency words).
- `localize()` turns the most common built-in answers (live status, arrival, ETA, safety messages) into
  Hindi and Bengali. Other languages get the built-in answer in English rather than a guessed translation.
- Keyword lists below were written without a native-speaker review – have them checked before launch.
"""
import re

SUPPORTED = {"en": "English", "hi": "Hindi", "bn": "Bengali", "ta": "Tamil", "te": "Telugu", "mr": "Marathi",
             "gu": "Gujarati", "kn": "Kannada", "ml": "Malayalam", "pa": "Punjabi", "or": "Odia", "ur": "Urdu",
             "as": "Assamese"}
_SCRIPT = {"hi": "Devanagari", "bn": "Bengali", "ta": "Tamil", "te": "Telugu", "mr": "Devanagari", "gu": "Gujarati",
           "kn": "Kannada", "ml": "Malayalam", "pa": "Gurmukhi", "or": "Odia", "ur": "Urdu (Nastaliq)", "as": "Assamese"}
PROMPT_NAME = {"en": "English (Hinglish is fine if the parent uses it)",
               **{k: f"{v} in {_SCRIPT[k]} script" for k, v in SUPPORTED.items() if k != "en"}}


def norm(lang: str | None) -> str:
    return lang if lang in SUPPORTED else "en"


# ---------------------------------------------------------------- question -> English keywords
# Words are matched as prefixes so inflections ("स्कूल", "স্কুলে", "পৌঁছেছে") hit; 1–2 letter words match exactly.
_WORDS = {
    # Hindi
    "कहाँ": "where", "कहां": "where", "किधर": "where", "कब": "when", "अभी": "now", "स्कूल": "school",
    "विद्यालय": "school", "घर": "home", "पहुँचेग": "will reach", "पहुंचेग": "will reach", "पहुँच": "reached", "पहुंच": "reached", "निकल": "left", "आज": "today", "कल": "yesterday",
    "बैटरी": "battery", "सुरक्षित": "safe", "ठीक": "ok", "ट्यूशन": "tuition", "बस": "bus", "हफ्ते": "week",
    "हफ़्ते": "week", "सप्ताह": "week", "देर": "late", "लेट": "late", "समस्या": "problem", "दिक्कत": "problem",
    "खो": "missing", "गुम": "missing", "बचाओ": "emergency", "खतरा": "danger", "ख़तरा": "danger", "खतरे": "danger",
    "आएगा": "will come home", "आएगी": "will come home", "आयेगा": "will come home", "आयेगी": "will come home",
    "लौटेगा": "will come home", "लौटेगी": "will come home",
    # Bengali
    "কোথায়": "where", "কোথায়": "where", "কখন": "when", "এখন": "now", "স্কুল": "school", "বিদ্যালয়": "school",
    "বাড়ি": "home", "বাড়ি": "home", "বাড়ী": "home", "বাসা": "home", "পৌঁছাবে": "will reach", "পৌছাবে": "will reach", "পৌঁছ": "reached", "পৌছ": "reached", "বেরিয়ে": "left", "বেরিয়ে": "left",
    "আজ": "today", "আজকে": "today", "গতকাল": "yesterday", "কাল": "yesterday", "ব্যাটারি": "battery",
    "নিরাপদ": "safe", "ঠিক": "ok", "টিউশন": "tuition", "বাস": "bus", "সপ্তাহ": "week", "দেরি": "late",
    "দেরী": "late", "সমস্যা": "problem", "হারিয়ে": "missing", "হারিয়ে": "missing", "বাঁচাও": "emergency",
    "বিপদ": "danger", "ফিরবে": "will come home", "আসবে": "will come home",
    # Assamese (Bengali script; shared words above)
    "ক'ত": "where", "কেতিয়া": "when", "এতিয়া": "now", "ঘৰ": "home", "আজি": "today", "কালি": "yesterday",
    # Marathi
    "कुठे": "where", "कधी": "when", "आता": "now", "शाळ": "school", "घरी": "home", "पोहोच": "reached",
    "काल": "yesterday", "बॅटरी": "battery", "उशीर": "late", "धोका": "danger", "हरवल": "missing", "वाचवा": "emergency",
    "येईल": "will come home",
    # Tamil
    "எங்கே": "where", "எங்கு": "where", "எப்போது": "when", "இப்போது": "now", "பள்ளி": "school", "ஸ்கூல்": "school",
    "வீடு": "home", "வீட்டு": "home", "சேர்ந்": "reached", "அடைந்": "reached", "இன்று": "today", "நேற்று": "yesterday",
    "பேட்டரி": "battery", "பாதுகாப்பா": "safe", "தாமத": "late", "ஆபத்து": "danger", "காணவில்லை": "missing",
    "காப்பாற்று": "emergency", "வருவா": "will come home",
    # Telugu
    "ఎక్కడ": "where", "ఎప్పుడు": "when", "ఇప్పుడు": "now", "బడి": "school", "పాఠశాల": "school", "స్కూల్": "school",
    "ఇంటి": "home", "ఇల్లు": "home", "చేర": "reached", "ఈరోజు": "today", "నిన్న": "yesterday", "బ్యాటరీ": "battery",
    "సురక్షిత": "safe", "ఆలస్య": "late", "ప్రమాద": "danger", "కనిపించ": "missing", "కాపాడ": "emergency",
    "వస్తా": "will come home",
    # Gujarati
    "ક્યાં": "where", "ક્યારે": "when", "હમણાં": "now", "અત્યારે": "now", "શાળા": "school", "સ્કૂલ": "school",
    "ઘર": "home", "પહોંચ": "reached", "આજે": "today", "ગઈકાલે": "yesterday", "બેટરી": "battery", "સુરક્ષિત": "safe",
    "મોડ": "late", "ખતરો": "danger", "ગુમ": "missing", "બચાવો": "emergency", "આવશે": "will come home",
    # Kannada
    "ಎಲ್ಲಿ": "where", "ಯಾವಾಗ": "when", "ಈಗ": "now", "ಶಾಲೆ": "school", "ಸ್ಕೂಲ್": "school", "ಮನೆ": "home",
    "ತಲುಪ": "reached", "ಇಂದು": "today", "ನಿನ್ನೆ": "yesterday", "ಬ್ಯಾಟರಿ": "battery", "ಸುರಕ್ಷಿತ": "safe",
    "ತಡ": "late", "ಅಪಾಯ": "danger", "ಕಾಣೆ": "missing", "ಕಾಪಾಡಿ": "emergency", "ಬರುತ್ತಾ": "will come home",
    # Malayalam
    "എവിടെ": "where", "എപ്പോൾ": "when", "ഇപ്പോൾ": "now", "സ്കൂൾ": "school", "വിദ്യാലയ": "school", "വീട്": "home",
    "വീട്ടി": "home", "എത്ത": "reached", "എത്തി": "reached", "ഇന്ന്": "today", "ഇന്നലെ": "yesterday",
    "ബാറ്ററി": "battery", "സുരക്ഷിത": "safe", "വൈകി": "late", "അപകട": "danger", "കാണാതായ": "missing",
    "രക്ഷിക്ക": "emergency", "വരും": "will come home",
    # Punjabi
    "ਕਿੱਥੇ": "where", "ਕਿਥੇ": "where", "ਕਦੋਂ": "when", "ਹੁਣ": "now", "ਸਕੂਲ": "school", "ਘਰ": "home",
    "ਪਹੁੰਚ": "reached", "ਅੱਜ": "today", "ਕੱਲ੍ਹ": "yesterday", "ਬੈਟਰੀ": "battery", "ਸੁਰੱਖਿਅਤ": "safe", "ਦੇਰ": "late",
    "ਖ਼ਤਰ": "danger", "ਖਤਰ": "danger", "ਗੁੰਮ": "missing", "ਬਚਾਓ": "emergency", "ਆਵੇਗ": "will come home",
    # Odia
    "କେଉଁଠି": "where", "କେବେ": "when", "ଏବେ": "now", "ସ୍କୁଲ": "school", "ବିଦ୍ୟାଳୟ": "school", "ଘର": "home",
    "ପହଞ୍ଚ": "reached", "ଆଜି": "today", "ଗତକାଲି": "yesterday", "ବ୍ୟାଟେରୀ": "battery", "ସୁରକ୍ଷିତ": "safe",
    "ବିଳମ୍ବ": "late", "ବିପଦ": "danger", "ହଜି": "missing", "ବଞ୍ଚାଅ": "emergency", "ଆସିବ": "will come home",
    # Urdu
    "کہاں": "where", "کب": "when", "ابھی": "now", "اسکول": "school", "سکول": "school", "گھر": "home",
    "پہنچ": "reached", "آج": "today", "کل": "yesterday", "بیٹری": "battery", "محفوظ": "safe", "دیر": "late",
    "خطرہ": "danger", "گم": "missing", "بچاؤ": "emergency", "آئے": "will come home",
}
try:                                             # extra words per language (future tense, "left", …)
    from .lang_answers_tr import EXTRA_WORDS
    _WORDS.update(EXTRA_WORDS)
except ImportError:
    pass
_PREFIX = sorted((w for w in _WORDS if len(w) >= 3), key=len, reverse=True)
_NATIVE = re.compile(r"[؀-ۿऀ-෿]")      # Urdu + all Indic scripts


def is_native(text: str) -> bool:
    return bool(_NATIVE.search(text or ""))


def keywords(question: str) -> str:
    """Replace Hindi/Bengali words with English keywords; other text is kept as is."""
    if not is_native(question):
        return question
    out = []
    for tok in re.split(r"(\s+|[?,.!।؟۔،]+)", question):
        w = tok.strip()
        hit = _WORDS.get(w) or next((_WORDS[p] for p in _PREFIX if w.startswith(p)), None)
        out.append(hit if hit else tok)
    return "".join(out)


# ---------------------------------------------------------------- built-in answers -> language
from .lang_answers import ANS  # noqa: E402


def _T(lang: str, key: str, **kw) -> str:
    tpl = ANS.get(lang, {}).get(key) or ANS["en"][key]
    try:
        return tpl.format(**kw)
    except (KeyError, IndexError, ValueError):
        return ANS["en"][key].format(**kw)


def _p(name: str | None, lang: str) -> str:
    n = (name or "").strip()
    return ANS.get(lang, {}).get("place_" + n.lower()) or n


def _ago(s: str, lang: str) -> str:
    s = s.strip()
    if s == "just now":
        return _T(lang, "just_now")
    m = re.fullmatch(r"(\d+) (min|h|d)\w* ago", s)
    return _T(lang, {"min": "ago_min", "h": "ago_h", "d": "ago_d"}[m[2]], n=m[1]) if m else s


def _day(word: str, lang: str) -> str | None:
    return _T(lang, word) if word in ("today", "yesterday") else None


def _status(m, g):
    mv = _T(g, "moving", s=m["s"]) if m["s"] else ""
    kw = dict(l=m["l"], mv=mv, t=m["t"], fresh=_ago(m["f"], g))
    if m["n"]:
        return _T(g, "status_near", n=m["n"].strip(), **kw)
    if m["p"]:
        return _T(g, "status_known", p=_p(m["p"], g), **kw)
    return _T(g, "status_unknown", **kw)


def _trip(m, g):
    out = _T(g, "trip", f=_p(m["f"], g), t=m["t"], k=m["k"])
    if m["d"]:
        out += _T(g, "trip_heading", d=_p(m["d"], g), e=m["e"], n=m["n"])
    return out + _T(g, "end")


def _reached(m, g):
    d = _day(m["d"], g)
    if d is None:
        return m[0]
    kw = dict(l=m["l"], p=_p(m["p"], g), t=m["t"], day=d)
    return _T(g, "reached_still", **kw) if m["still"] else _T(g, "reached_left", left=m["left"], **kw)


def _not_there(m, g):
    d = _day(m["d"], g)
    if d is None:
        return m[0]
    kw = dict(l=m["l"], p=_p(m["p"], g), day=d)
    return _T(g, "not_there_n", n=m["n"], **kw) if m["n"] else _T(g, "not_there_none", **kw)


def _on_way(m, g):
    out = _T(g, "on_way", l=m["l"], p=_p(m["p"], g), t=m["t"], n=m["n"], k=m["k"])
    return out + (_T(g, "usual_trip", u=m["u"]) if m["u"] else "")


# (English sentence written by the planner, builder(match, lang))
_RULES = [
    (r"📍 (?P<l>.+?) is (?:at a place not in the routine|near (?P<n>[^(]+?)|at (?P<p>[^,(]+?))(?:, moving at (?P<s>\d+) km/h)? "
     r"\(updated (?P<t>[\d:]+), (?P<f>[^)]+)\)\.", _status),
    (r" ✅ That's where (?P<l>.+?) usually is at this time\.", lambda m, g: _T(g, "usual_here", l=m["l"])),
    (r" Note: usually (?P<l>.+?) is at (?P<p>.+?) at this time\.",
     lambda m, g: _T(g, "usual_other", l=m["l"], p=_p(m["p"], g))),
    (r"🚶 Left (?P<f>.+?) at (?P<t>[\d:]+) · (?P<k>[\d.]+) km so far(?: · heading to (?P<d>.+?), expected ~(?P<e>[\d:]+) "
     r"\((?P<n>\d+) min\))?\.", _trip),
    (r"🚶 (?P<l>.+?) left (?P<f>.+?) at (?P<t>[\d:]+) and is on the way to (?P<d>.+?) – about (?P<k>[\d.]+) km left\. "
     r"Expected around (?P<e>[\d:]+) \(~(?P<n>\d+) min, estimate from today's speed\)\.",
     lambda m, g: _T(g, "on_way_live", l=m["l"], f=_p(m["f"], g), t=m["t"], d=_p(m["d"], g), k=m["k"], e=m["e"], n=m["n"])),
    (r"🔋 Battery (?P<b>[\d–]+)%", lambda m, g: _T(g, "battery", b=m["b"])),
    (r"✅ No SOS\.", lambda m, g: _T(g, "no_sos")),
    (r"🚨 SOS ACTIVE – open the SOS screen\.", lambda m, g: _T(g, "sos_active")),
    (r"✅ (?P<l>.+?) reached (?P<p>.+?) at (?P<t>[\d:]+) (?P<d>\w+)(?: and is (?P<still>still) there\.| and left around "
     r"(?P<left>[\d:]+)\.)", _reached),
    (r"❗ (?P<l>.+?) has not been at (?P<p>.+?) (?P<d>\w+)(?: \((?P<n>\d+) tracker reports that day\)\.| – no tracker data\.)",
     _not_there),
    (r"🏠 (?P<l>.+?) is already at (?P<p>.+?) \(updated (?P<t>[\d:]+)\)\.",
     lambda m, g: _T(g, "already", l=m["l"], p=_p(m["p"], g), t=m["t"])),
    (r"🚶 (?P<l>.+?) is on the way to (?P<p>.+?)\. Expected at (?P<t>[\d:]+) \(about (?P<n>\d+) min, (?P<k>[\d.]+) km left\)\."
     r"(?: Usually this trip takes (?P<u>\d+) min\.)?", _on_way),
    (r"⚠️ The tracker is OFFLINE – no update for (?P<a>[^,]+?), so this is not live\.", lambda m, g: _T(g, "offline", a=m["a"])),
    (r"Please call or check the tracker is charged and switched on\.", lambda m, g: _T(g, "call_check")),
    (r"No report from (?P<l>.+?)'s tracker yet\.", lambda m, g: _T(g, "no_report", l=m["l"])),
    # safety messages from guardrails – these matter most, so they are fully translated
    (r"🚨 If you think (?P<l>.+?) is in danger, call 112 now\. In the app: .*?so nearby people can help\.",
     lambda m, g: _T(g, "emergency", l=m["l"])),
    (r"I'm sorry you're going through this\..*?please reach out to someone you trust\.", lambda m, g: _T(g, "crisis")),
    (r"Sorry, that's out of scope – I can only answer questions about (?P<l>.+?)'s tracker.*",
     lambda m, g: _T(g, "out_of_scope", l=m["l"])),
]
_RULES = [(re.compile(p, re.S), r) for p, r in _RULES]


def localize(text: str, lang: str | None) -> str:
    """Rewrite the English built-in answer in `lang` (every language that has an ANS table)."""
    lang = norm(lang)
    if lang == "en" or lang not in ANS or not text:
        return text
    for rx, build in _RULES:
        text = rx.sub(lambda m: build(m, lang), text)
    return text
