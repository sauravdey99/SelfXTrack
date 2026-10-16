"""Phase 6: simple per-IP rate limiting for sensitive endpoints + security headers.
In-memory (one server instance). Behind several instances use a shared store (Redis) or the proxy's limiter."""
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .config import settings

LIMITED = ("/api/auth/login", "/api/auth/register", "/api/auth/otp/request", "/api/auth/otp/verify",
           "/api/auth/password/forgot", "/api/auth/password/reset", "/api/devices/claim")


def client_ip(request) -> str:
    """Real client IP. X-Forwarded-For is trusted only when the request comes from our own proxy (Caddy),
    otherwise anyone could send a fake header to dodge the limit."""
    peer = request.client.host if request.client else "?"
    trusted = {p.strip() for p in settings.trusted_proxies.split(",") if p.strip()}
    if peer in trusted:
        fwd = request.headers.get("x-forwarded-for", "").split(",")[-1].strip()   # address our proxy saw
        return fwd or peer
    return peer


class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.hits: dict[str, deque] = defaultdict(deque)

    async def dispatch(self, request, call_next):
        path = request.url.path
        if request.method == "POST" and path in LIMITED:
            ip = client_ip(request)
            q, now = self.hits[f"{ip}|{path}"], time.monotonic()
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= settings.rate_limit_per_minute:
                return JSONResponse({"detail": "Too many attempts. Please wait a minute."}, status_code=429)
            q.append(now)
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        if settings.env == "production":
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return resp
