"""Guardrails for the "Ask about <child>" assistant.

Runs BEFORE any engine (local planner or LLM) and AFTER an LLM answer. Decisions are rule-based so they are
predictable, testable and work without an AI model.

Input checks (in this order):
  1. empty / too long / too many questions per hour
  2. emergency words ("missing", "kidnapped", "not answering"…) -> urgent guidance first (112, SOS screen) + live status
  3. crisis / self-harm language -> supportive message with Indian helplines (no tracking answer)
  4. prompt-injection / jailbreak attempts -> refused
  5. tracking OTHER people (spouse, neighbour, someone's phone) -> refused (privacy)
  6. requests to DO things (send SOS, delete history, call…) -> explained where in the app, the assistant is read-only
  7. medical / legal questions -> out of scope, see a professional
  8. anything not about this child's tracker -> "out of scope" with examples

Output checks (LLM answers only): length cap, no system-prompt leakage, no "definitely safe" claims,
no markdown tables, and an out-of-scope token from the model is turned into our standard message.
"""
import re
import time
from collections import defaultdict, deque

MAX_LEN = 300
MAX_PER_HOUR = 60
_hits: dict[int, deque] = defaultdict(deque)

OUT_TOKEN = "OUT_OF_SCOPE"

EMERGENCY = re.compile(r"\b(missing|kidnap\w*|abduct\w*|lost|not (answering|picking|responding)|can'?t (find|reach)|"
                       r"cannot (find|reach)|danger|accident|attack\w*|stranger|someone (took|is following)|help me|"
                       r"emergency|bachao|kho gaya|gum ho)\b", re.I)
CRISIS = re.compile(r"\b(suicid\w*|kill (myself|himself|herself)|end (my|his|her) life|self[- ]?harm|"
                    r"want to die|hurt (myself|himself|herself))\b", re.I)
INJECTION = re.compile(r"(ignore (all|any|the|previous|above)|disregard (the|all|previous)|system prompt|"
                       r"developer mode|jailbreak|you are now|act as|pretend (to be|you)|reveal (your|the) (prompt|instructions)|"
                       r"forget (your|all) (rules|instructions)|\bDAN\b|override (the )?rules)", re.I)
OTHER_PEOPLE = re.compile(r"\b(my (wife|husband|girlfriend|boyfriend|partner|ex|neighbou?r|boss|employee|maid|driver)|"
                          r"someone'?s (phone|location)|(his|her) phone number|other (child|kid|people|users?|families)|"
                          r"another (child|kid|person|user)|track (a|any|some) ?(one|body|person|number|phone))\b", re.I)
ACTIONS = re.compile(r"\b(send|trigger|raise|start|cancel|stop|turn off|switch off|disable|delete|remove|erase|"
                     r"call|message|sms|share|unlink|change|set|add|book|pay|buy|unsubscribe)\b.{0,30}"
                     r"\b(sos|alarm|alert|tracker|history|location|link|school|police|zone|family|plan|subscription|him|her)\b",
                     re.I)
MEDICAL_LEGAL = re.compile(r"\b(fever|medicine|tablet|doctor|diagnos\w*|symptom\w*|injur\w*|bleeding|vomit\w*|"
                           r"lawyer|legal|court|police complaint|fir\b|custody|divorce)\b", re.I)

# words that make a question "about the tracker"
IN_SCOPE = re.compile(r"\b(where|when|what time|location|located|place|reach\w*|arriv\w*|left|leave|leaving|went|go|going|"
                      r"come|coming|came|back|return\w*|home|school|tuition|coaching|bus|class|safe\w*|ok|okay|fine|"
                      r"status|sos|alert\w*|unusual|problem|issue|late|early|on time|route|trip|travel\w*|distance|km|"
                      r"speed|fast|battery|charge\w*|online|offline|tracker|eta|expected|today|yesterday|week|month|"
                      r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|morning|evening|night|"
                      r"usual\w*|routine|summary|day|history|how many|times|average|now|kahan|kab|pahunch\w*)\b", re.I)


def _rate_limited(user_id: int | None) -> bool:
    if user_id is None:
        return False
    q, now = _hits[user_id], time.monotonic()
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= MAX_PER_HOUR:
        return True
    q.append(now)
    return False


def examples(label: str) -> str:
    return (f"“Where is {label} now?”, “Did {label} reach school?”, “When will {label} come home?”, "
            f"“Any problem this week?”, “Battery?”")


def check_input(question: str, label: str, places: list[str], user_id: int | None = None,
                strict_scope: bool = True) -> dict | None:
    """Returns None if the question may go to the engines, else {"category", "answer", "status"}.
    status=True means: append the child's live status to the answer.
    strict_scope=False skips the keyword scope check (regional-language question going to an LLM, which has
    its own OUT_OF_SCOPE rule) – all safety checks still run."""
    q = (question or "").strip()
    if len(q) < 2:
        return {"category": "empty", "answer": f"Please type a question about {label}, e.g. {examples(label)}"}
    if len(q) > MAX_LEN:
        return {"category": "too_long", "answer": f"Please keep the question short (under {MAX_LEN} characters)."}
    if _rate_limited(user_id):
        return {"category": "rate_limit", "answer": "Too many questions in the last hour – please try again later. "
                "SOS and safety alerts keep working as usual."}
    if CRISIS.search(q):
        return {"category": "crisis", "answer":
                "I'm sorry you're going through this. If anyone is in immediate danger, call 112 now. "
                "For support you can call Tele-MANAS on 14416 (free, 24×7) or the Childline on 1098. "
                "You're not alone – please reach out to someone you trust."}
    if EMERGENCY.search(q):
        return {"category": "emergency", "status": True, "answer":
                f"🚨 If you think {label} is in danger, call 112 now. In the app: open {label}'s SOS / map screen → "
                "Navigate, share the live link, or press Emergency – School / Emergency – Group (Smart plan) "
                "so nearby people can help."}
    if INJECTION.search(q):
        return {"category": "injection", "answer":
                f"I can't change how I work. I only answer questions about {label}'s tracker, e.g. {examples(label)}"}
    if OTHER_PEOPLE.search(q):
        return {"category": "privacy", "answer":
                f"For privacy I can only answer about {label}'s tracker in your family account – not about other "
                "people or phones. Tracking someone without their consent is not allowed."}
    if ACTIONS.search(q) and not re.search(r"^\s*(did|has|was|is|when|where|what)\b", q, re.I):
        return {"category": "action", "answer":
                "I can only look at the tracker data – I can't change anything or send alerts. In the app: "
                "SOS screen → Call 112 / Emergency – School / Group · Map → 🔗 live link · ⚙️ Child setup → school, "
                "family, bus · 🏅 Plans."}
    if MEDICAL_LEGAL.search(q) and not IN_SCOPE.search(q):
        return {"category": "out_of_scope_professional", "answer":
                "That's outside what I can help with – please ask a doctor or a lawyer. "
                f"I can tell you about {label}'s location, arrivals and safety alerts."}
    name_hit = label.lower() in q.lower() or any(p.lower() in q.lower() for p in places)
    if strict_scope and not IN_SCOPE.search(q) and not name_hit:
        return {"category": "out_of_scope", "answer":
                f"Sorry, that's out of scope – I can only answer questions about {label}'s tracker "
                f"(location, arrivals, trips, alerts, battery). Try: {examples(label)}"}
    return None


SAFE_CLAIM = re.compile(r"\b(he|she|they|\w+) (is|are) (definitely|completely|totally|100%) safe\b", re.I)


def check_output(answer: str, label: str) -> str:
    """Clean an LLM answer before it reaches the parent."""
    a = (answer or "").strip()
    if not a or OUT_TOKEN in a:
        return (f"Sorry, that's out of scope – I can only answer questions about {label}'s tracker. "
                f"Try: {examples(label)}")
    if re.search(r"(system prompt|my instructions|as an ai language model)", a, re.I):
        return f"I can only answer questions about {label}'s tracker. Try: {examples(label)}"
    a = SAFE_CLAIM.sub(lambda m: f"{m.group(1)} {m.group(2)} – based on the tracker data – okay", a)
    a = re.sub(r"^\s*\|.*\|\s*$", "", a, flags=re.M)                       # no markdown tables
    a = re.sub(r"\*\*(.+?)\*\*", r"\1", a)                                   # no bold markdown
    if len(a) > 700:
        a = a[:700].rsplit(" ", 1)[0] + "…"
    return a
