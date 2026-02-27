import json
import logging
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi_csrf_protect import CsrfProtect
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from config import ALLOWED_ORIGINS, NOSTR_JSON_PATH, STATIC_DIR, WELL_KNOWN_DIR
from db.connection import init_db
from routers import admin_auth, admin_records, nip05, public
import services.payments as payments_svc
from services.payments import _validate_lnurl

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_real_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
        if client_ip:
            return client_ip
    return request.client.host if request.client else "unknown"


def get_rate_limit_key(request: Request) -> str:
    ip = get_real_ip(request)
    session_token = request.cookies.get("session_token", "")
    if session_token:
        return f"{ip}:{session_token}"
    return ip


# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_rate_limit_key)

# ── App factory ───────────────────────────────────────────────────────────────
app = FastAPI(title="NIP-05 Nostr Identifier")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda req, exc: __import__('fastapi').responses.JSONResponse(
    status_code=429, content={"detail": "Rate limit exceeded"}
))

STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
            "img-src 'self' data:; "
            "font-src 'self' https://cdnjs.cloudflare.com; "
            "connect-src 'self' https:; "
            "frame-ancestors 'none';"
        )
        return response


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(SlowAPIMiddleware)

# ── CSRF Protection ───────────────────────────────────────────────────────────
csrf_protect = CsrfProtect()


def generate_csrf_token():
    return csrf_protect.generate_csrf_token()


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(public.router)
app.include_router(nip05.router)
app.include_router(admin_auth.router)
app.include_router(admin_records.router)


# ── Lifecycle ─────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup() -> None:
    from config import LNURL
    _validate_lnurl(LNURL)
    payments_svc.http_client = httpx.AsyncClient(timeout=30.0)

    WELL_KNOWN_DIR.mkdir(exist_ok=True)
    for tmp_file in WELL_KNOWN_DIR.glob("*.tmp.json"):
        try:
            tmp_file.unlink()
            logger.info(f"Cleaned orphan temp file: {tmp_file}")
        except OSError:
            pass

    await init_db()

    if not NOSTR_JSON_PATH.exists():
        with open(NOSTR_JSON_PATH, "w") as f:
            json.dump({"names": {}}, f)


@app.on_event("shutdown")
async def shutdown() -> None:
    from db.connection import _db_pool
    if payments_svc.http_client:
        await payments_svc.http_client.aclose()
    import db.connection as _db_mod
    if _db_mod._db_pool:
        await _db_mod._db_pool.close()
        _db_mod._db_pool = None


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    from config import DOMAIN, INVOICE_AMOUNT_SATS
    logger.info("Starting NIP-05 Nostr Identifier server...")
    logger.info(f"Domain: {DOMAIN}")
    logger.info(f"Invoice amount: {INVOICE_AMOUNT_SATS} sats")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
