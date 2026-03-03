import json
import logging
import os
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from config import ALLOWED_ORIGINS, DOMAINS_LIST, NOSTR_DATA_DIR, PRIMARY_DOMAIN, STATIC_DIR, get_nostr_json_path
from db.connection import init_db
from routers import admin_auth, admin_records, nip05, public
import services.payments as payments_svc
from services.payments import _validate_lnurl

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ── App factory ───────────────────────────────────────────────────────────────
app = FastAPI(title="NIP-05 Nostr Identifier")
app.state.limiter = limiter


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.add_exception_handler(RateLimitExceeded, lambda req, exc: JSONResponse(
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
    allow_headers=["Content-Type", "Authorization"],
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

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(public.router)
app.include_router(nip05.router)
app.include_router(admin_auth.router)
app.include_router(admin_records.router)


# ── Lifecycle ─────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup() -> None:
    from config import LNURL
    from core.nostr import migrate_to_per_domain
    _validate_lnurl(LNURL)
    payments_svc.http_client = httpx.AsyncClient(timeout=30.0)

    # Create per-domain directories
    for domain_entry in DOMAINS_LIST:
        domain = domain_entry["domain"]
        domain_well_known = NOSTR_DATA_DIR / domain / ".well-known"
        domain_well_known.mkdir(parents=True, exist_ok=True)
        os.chmod(domain_well_known, 0o755)

    # Clean orphan temp files in each domain directory
    for tmp_file in NOSTR_DATA_DIR.rglob("*.tmp.json"):
        try:
            tmp_file.unlink()
            logger.info(f"Cleaned orphan temp file: {tmp_file}")
        except OSError:
            pass

    await init_db()

    # Migrate legacy centralized nostr.json to per-domain files
    migrate_to_per_domain()

    # Ensure each configured domain has a nostr.json file
    for domain_entry in DOMAINS_LIST:
        domain = domain_entry["domain"]
        nostr_json_path = get_nostr_json_path(domain)
        if not nostr_json_path.exists():
            nostr_json_path.parent.mkdir(parents=True, exist_ok=True)
            with open(nostr_json_path, "w") as f:
                json.dump({"names": {}}, f)
            os.chmod(nostr_json_path, 0o644)
            logger.info(f"Created empty nostr.json for {domain}")

    logger.info(f"Configured domains: {', '.join(d['domain'] + ':' + str(d['price']) + ' sats' for d in DOMAINS_LIST)}")


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
    logger.info("Starting NIP-05 Nostr Identifier server...")
    logger.info(f"Primary domain: {PRIMARY_DOMAIN}")
    logger.info(f"Configured domains: {', '.join(d['domain'] + ':' + str(d['price']) + ' sats' for d in DOMAINS_LIST)}")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
