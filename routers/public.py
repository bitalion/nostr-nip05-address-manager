import re
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import DOMAIN, INVOICE_AMOUNT_SATS, NOSTR_JSON_PATH, STATIC_DIR
from core.nostr import check_nip05_available, convert_npub_to_hex, load_nostr_json
from db.connection import get_db
from schemas import ConvertPubkeyRequest

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)

BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    try:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "domain": DOMAIN, "price_sats": INVOICE_AMOUNT_SATS}
        )
    except Exception as e:
        return HTMLResponse(content=f"Error: {str(e)}", status_code=500)


@router.get("/favicon.ico")
async def favicon():
    return FileResponse(STATIC_DIR / "images/favicon.ico")


@router.get("/health")
async def health():
    health_status = {"status": "healthy", "domain": DOMAIN}

    if NOSTR_JSON_PATH.exists():
        try:
            data = load_nostr_json()
            health_status["registered_users"] = len(data.get("names", {}))
        except Exception:
            health_status["status"] = "degraded"
            health_status["nostr_json"] = "error"
    else:
        health_status["status"] = "degraded"
        health_status["nostr_json"] = "not_found"

    status_code = 200 if health_status["status"] == "healthy" else 503
    return JSONResponse(content=health_status, status_code=status_code)


@router.get("/.well-known/nostr.json")
async def get_nostr_json():
    return JSONResponse(content=load_nostr_json())


@router.post("/api/convert-pubkey")
@limiter.limit("20/minute")
async def convert_pubkey(request: Request, data: ConvertPubkeyRequest):
    try:
        hex_key = convert_npub_to_hex(data.pubkey)
        return {"hex": hex_key}
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/api/check-pubkey")
@limiter.limit("20/minute")
async def check_pubkey(request: Request, data: ConvertPubkeyRequest):
    try:
        hex_key = convert_npub_to_hex(data.pubkey)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    nostr_data = load_nostr_json()
    for existing_hex in nostr_data.get("names", {}).values():
        if existing_hex.lower() == hex_key.lower():
            return {"hex": hex_key, "registered": True}
    return {"hex": hex_key, "registered": False}


@router.get("/api/check-availability/{username}")
@limiter.limit("30/minute")
async def check_availability(request: Request, username: str):
    if not re.match(r'^[a-zA-Z0-9_-]{1,30}$', username):
        raise HTTPException(status_code=400, detail="Invalid username format")
    available = await check_nip05_available(username.strip())
    return {"available": available}


@router.get("/api/latest-records")
@limiter.limit("30/minute")
async def latest_records(request: Request):
    import aiosqlite
    db = await get_db()
    db.row_factory = aiosqlite.Row
    cursor = await db.execute(
        """SELECT nip05, npub, payment_completed, in_nostr_json, admin_only, updated_at
           FROM records ORDER BY id DESC LIMIT 5"""
    )
    rows = await cursor.fetchall()

    result = []
    for row in rows:
        nip05 = row["nip05"]
        npub = row["npub"]

        if "@" in nip05:
            parts = nip05.split("@")
            username = parts[0]
            protected_nip05 = f"***@{parts[1]}" if len(username) <= 3 else f"***{username[3:]}@{parts[1]}"
        else:
            protected_nip05 = nip05

        if npub and len(npub) > 20:
            protected_npub = f"npub1{'*' * 8}{npub[8:-8]}{'*' * 8}"
        else:
            protected_npub = npub

        result.append({
            "nip05": protected_nip05,
            "npub": protected_npub,
            "in_nostr_json": bool(row["in_nostr_json"]),
            "payment_completed": bool(row["payment_completed"]),
            "admin_only": bool(row["admin_only"]),
            "updated_at": row["updated_at"],
        })

    return result
