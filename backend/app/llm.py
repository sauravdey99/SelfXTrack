"""Optional Claude API helper. Used ONLY to write text (summaries, answers) from verified data.
If SELFX_ANTHROPIC_API_KEY is not set or the call fails, callers fall back to template text."""
import json
import logging

import httpx

from .config import settings

log = logging.getLogger("selfx.llm")

SYSTEM = ("You are the SelfXTrack safety assistant for parents in India. Answer ONLY from the JSON data given. "
          "Always mention exact times (24h, IST). If the data does not contain the answer, say so plainly. "
          "Never guess a location, never claim the child is safe or in danger beyond the data, and never give "
          "medical or legal advice. Never mention coordinates, number of reports or other technical data. "
          "Keep answers short (max 3 sentences), simple English.")


def provider() -> str | None:
    if settings.llm_provider:
        return None if settings.llm_provider.lower() in ("none", "off", "local") else settings.llm_provider
    if settings.anthropic_api_key:
        return "anthropic"
    if settings.llm_api_key or "api.openai.com" not in settings.llm_base_url:
        return "openai"            # OpenAI-compatible (Gemini / Groq / Ollama …)
    return None


def enabled() -> bool:
    return provider() is not None


def _openai_chat(messages: list[dict], tools: list | None = None, max_tokens: int = 400) -> dict:
    headers = {"content-type": "application/json"}
    if settings.llm_api_key:
        headers["authorization"] = f"Bearer {settings.llm_api_key}"
    body = {"model": settings.llm_model, "max_tokens": max_tokens, "messages": messages, "temperature": 0.2}
    if tools:
        body["tools"] = tools
    import time
    for attempt in range(3):                 # free tiers (Groq) answer 429 when busy -> wait briefly and retry
        r = httpx.post(settings.llm_base_url.rstrip("/") + "/chat/completions", headers=headers, json=body, timeout=60)
        if r.status_code not in (429, 503) or attempt == 2:
            break
        try:
            wait = float(r.headers.get("retry-after") or 2)
        except ValueError:
            wait = 2
        time.sleep(min(max(wait, 1), 6))
    r.raise_for_status()
    return r.json()["choices"][0]["message"]


def complete(task: str, data: dict, max_tokens: int = 800) -> str | None:
    if not enabled():
        return None
    if provider() == "openai":
        try:
            m = _openai_chat([{"role": "system", "content": SYSTEM},
                              {"role": "user", "content": f"{task}\n\nDATA:\n{json.dumps(data, default=str)}"}],
                             max_tokens=max_tokens)
            return (m.get("content") or "").strip() or None
        except Exception as e:
            log.warning("LLM failed: %s", e)
            return None
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": settings.anthropic_model, "max_tokens": max_tokens, "system": SYSTEM,
                  "messages": [{"role": "user", "content": f"{task}\n\nDATA:\n{json.dumps(data, default=str)}"}]},
            timeout=20,
        )
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json().get("content", [])).strip() or None
    except Exception as e:  # never break the app because of the AI
        log.warning("Claude API failed: %s", e)
        return None
