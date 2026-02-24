import logging
import os
import json
import re
import secrets
import tempfile
import shutil
import fcntl
import uuid
import time
from pathlib import Path
import aiosqlite
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address
import bech32
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

load_dotenv()

app = FastAPI(title="NIP-05 Nostr Identifier")
app.state.limiter = limiter

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
WELL_KNOWN_DIR = BASE_DIR / ".well-known"
NOSTR_JSON_PATH = WELL_KNOWN_DIR / "nostr.json"
DB_PATH = BASE_DIR / "registro.sqlite"

STATIC_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

LNURL = os.getenv("LNBITS_URL", "")
LNKEY = os.getenv("LNBITS_API_KEY", "")
INVOICE_AMOUNT_SATS = int(os.getenv("INVOICE_AMOUNT_SATS", "100"))
DOMAIN = os.getenv("DOMAIN", "example.com")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "").split(",") if os.getenv("ALLOWED_ORIGINS") else []
if not ALLOWED_ORIGINS:
    ALLOWED_ORIGINS = [f"https://{DOMAIN}"] if DOMAIN != "example.com" else []

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; img-src 'self' data:; font-src 'self' https://cdnjs.cloudflare.com; connect-src 'self';"
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

WELL_KNOWN_DIR.mkdir(exist_ok=True)

for tmp_file in WELL_KNOWN_DIR.glob("*.tmp.json"):
    try:
        tmp_file.unlink()
        logger.info(f"Cleaned orphan temp file: {tmp_file}")
    except OSError:
        pass


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS registros (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                nip05            TEXT    NOT NULL,
                npub             TEXT    NOT NULL,
                pubkey_hex       TEXT    NOT NULL,
                lightning_invoice TEXT,
                payment_hash     TEXT    UNIQUE,
                pago_completado  INTEGER NOT NULL DEFAULT 0,
                fecha_registro   INTEGER NOT NULL,
                en_nostr_json    INTEGER NOT NULL DEFAULT 0
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_payment_hash ON registros(payment_hash)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_nip05 ON registros(nip05)")
        await db.commit()
    logger.info(f"Database initialized at {DB_PATH}")


async def db_insert_registro(
    nip05: str,
    npub: str,
    pubkey_hex: str,
    lightning_invoice: str | None = None,
    payment_hash: str | None = None,
    pago_completado: bool = False,
    en_nostr_json: bool = False,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO registros
               (nip05, npub, pubkey_hex, lightning_invoice, payment_hash,
                pago_completado, fecha_registro, en_nostr_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                nip05, npub, pubkey_hex, lightning_invoice, payment_hash,
                1 if pago_completado else 0,
                int(time.time()),
                1 if en_nostr_json else 0,
            ),
        )
        await db.commit()
        logger.info(f"DB insert registro id={cursor.lastrowid} nip05={nip05}")
        return cursor.lastrowid


async def db_update_pago(payment_hash: str, en_nostr_json: bool = True) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE registros
               SET pago_completado = 1, en_nostr_json = ?
               WHERE payment_hash = ?""",
            (1 if en_nostr_json else 0, payment_hash),
        )
        await db.commit()
    logger.info(f"DB pago actualizado payment_hash={payment_hash[:16]}… en_nostr_json={en_nostr_json}")


http_client: httpx.AsyncClient | None = None


@app.on_event("startup")
async def startup() -> None:
    global http_client
    http_client = httpx.AsyncClient(timeout=30.0)
    await init_db()
    # Initialize nostr.json only after the DB is ready to avoid a partially
    # functional state if DB initialization fails
    if not NOSTR_JSON_PATH.exists():
        with open(NOSTR_JSON_PATH, "w") as f:
            json.dump({"names": {}}, f)


@app.on_event("shutdown")
async def shutdown() -> None:
    global http_client
    if http_client:
        await http_client.aclose()


def convert_npub_to_hex(npub: str) -> str:
    if npub.startswith("npub"):
        try:
            hrp, data = bech32.bech32_decode(npub)
            if hrp != "npub" or data is None:
                raise ValueError("Invalid npub format")
            converted = bech32.convertbits(data, 5, 8, False)
            if converted is None:
                raise ValueError("Invalid npub conversion")
            return ''.join(f'{x:02x}' for x in converted)
        except Exception as e:
            raise ValueError(f"Invalid npub format: {e}")
    elif re.match(r"^[0-9a-fA-F]{64}$", npub):
        return npub.lower()
    else:
        raise ValueError("Key must be npub or 64-character hex")


NOSTR_JSON_BACKUP = BASE_DIR / "nostr.json.bak"  # outside .well-known to avoid public exposure


def load_nostr_json() -> dict:
    try:
        with open(NOSTR_JSON_PATH, "r") as f:
            data = json.load(f)
            logger.info(f"Loaded nostr.json with {len(data.get('names', {}))} entries")
            return data
    except FileNotFoundError:
        logger.warning(f"nostr.json not found at {NOSTR_JSON_PATH}")
    except json.JSONDecodeError as e:
        logger.error(f"nostr.json is corrupt: invalid JSON at position {e.pos}")
        if NOSTR_JSON_BACKUP.exists():
            try:
                with open(NOSTR_JSON_BACKUP, "r") as f:
                    data = json.load(f)
                logger.info(f"Recovered {len(data.get('names', {}))} entries from backup")
                return data
            except (json.JSONDecodeError, OSError) as backup_err:
                logger.error(f"Backup is also corrupt")
    except OSError as e:
        logger.error(f"Error reading nostr.json: {e.filename or 'unknown file'}")
    return {"names": {}}


def save_nostr_json(data: dict) -> None:
    if not isinstance(data.get("names"), dict):
        raise ValueError("Invalid nostr.json structure: 'names' must be a dict")

    if NOSTR_JSON_PATH.exists():
        shutil.copy2(NOSTR_JSON_PATH, NOSTR_JSON_BACKUP)

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=NOSTR_JSON_PATH.parent, delete=False, suffix='.tmp.json') as tmp:
            json.dump(data, tmp, indent=2)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = tmp.name
        shutil.move(tmp_path, NOSTR_JSON_PATH)
        logger.info(f"Saved nostr.json with {len(data.get('names', {}))} entries")
    except Exception:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


LOCK_FILE = NOSTR_JSON_PATH.with_suffix(".lock")



def check_nip05_available(nip05: str) -> bool:
    lock_fd = None
    try:
        lock_fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_RDWR)
        fcntl.flock(lock_fd, fcntl.LOCK_SH)
        try:
            data = load_nostr_json()
            nip05_lower = nip05.lower().strip()
            for existing_nip05 in data.get("names", {}).keys():
                if existing_nip05.lower() == nip05_lower:
                    return False
            return True
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
    finally:
        if lock_fd is not None:
            os.close(lock_fd)


def check_and_add_nip05_entry(username: str, pubkey_hex: str) -> bool:
    lock_fd = None
    try:
        lock_fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_RDWR)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            data = load_nostr_json()
            if "names" not in data:
                data["names"] = {}
            
            username_lower = username.lower().strip()
            for existing_nip05 in data.get("names", {}).keys():
                if existing_nip05.lower() == username_lower:
                    return False
            
            data["names"][username] = pubkey_hex
            save_nostr_json(data)
            logger.info(f"Added NIP-05 entry for user: {username}")
            return True
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
    finally:
        if lock_fd is not None:
            os.close(lock_fd)


class ValidatedUsernameMixin:
    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not re.match(r'^[a-zA-Z0-9_-]{1,30}$', v):
            raise ValueError('Username must be 1-30 characters, letters, numbers, underscores or hyphens only')
        return v


class ValidatedPubkeyMixin:
    @field_validator('pubkey')
    @classmethod
    def validate_pubkey(cls, v: str) -> str:
        try:
            convert_npub_to_hex(v)
        except ValueError as e:
            raise ValueError(str(e))
        return v


class NIP05Request(ValidatedUsernameMixin, ValidatedPubkeyMixin, BaseModel):
    username: str
    pubkey: str


class ConvertPubkeyRequest(ValidatedPubkeyMixin, BaseModel):
    pubkey: str


class CheckPaymentRequest(ValidatedPubkeyMixin, ValidatedUsernameMixin, BaseModel):
    username: str
    pubkey: str
    payment_hash: str

    @field_validator('payment_hash')
    @classmethod
    def validate_payment_hash(cls, v: str) -> str:
        if not re.match(r'^[a-fA-F0-9]{64}$', v):
            raise ValueError('Invalid payment hash format')
        return v


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    try:
        return templates.TemplateResponse("index.html", {"request": request, "domain": DOMAIN, "price_sats": INVOICE_AMOUNT_SATS})
    except Exception as e:
        return HTMLResponse(content=f"Error: {str(e)}", status_code=500)


@app.get("/health")
async def health():
    health_status = {
        "status": "healthy",
        "domain": DOMAIN,
    }
    
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


@app.get("/.well-known/nostr.json")
async def get_nostr_json():
    return JSONResponse(content=load_nostr_json())


@app.post("/api/convert-pubkey")
@limiter.limit("20/minute")
async def convert_pubkey(request: Request, data: ConvertPubkeyRequest):
    try:
        hex_key = convert_npub_to_hex(data.pubkey)
        return {"hex": hex_key}
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/api/create-invoice")
@limiter.limit("10/minute")
async def create_invoice(request: Request, data: NIP05Request):
    try:
        username = data.username.strip()
        pubkey_hex = convert_npub_to_hex(data.pubkey)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not LNURL or not LNKEY:
        raise HTTPException(status_code=500, detail="Lightning payment not configured")

    try:
        response = await http_client.post(
            f"{LNURL}/api/v1/payments",
            headers={"X-Api-Key": LNKEY, "Content-Type": "application/json"},
            json={
                "out": False,
                "amount": INVOICE_AMOUNT_SATS,
                "memo": f"NIP-05: {username}@{DOMAIN}",
            },
        )
        if response.status_code not in (200, 201):
            logger.error(f"LNbits invoice creation failed: status={response.status_code}")
            raise HTTPException(status_code=500, detail="Failed to create invoice")

        invoice_data = response.json()
        logger.info(f"LNbits invoice created for {username}@{DOMAIN}")

        payment_request = (
            invoice_data.get("payment_request") or
            invoice_data.get("bolt11") or
            invoice_data.get("pr")
        )

        payment_hash = (
            invoice_data.get("payment_hash") or
            invoice_data.get("checking_id") or
            invoice_data.get("id")
        )

        if not payment_request:
            raise HTTPException(status_code=500, detail="No payment request in invoice data")

        await db_insert_registro(
            nip05=f"{username}@{DOMAIN}",
            npub=data.pubkey,
            pubkey_hex=pubkey_hex,
            lightning_invoice=payment_request,
            payment_hash=payment_hash,
        )

        return {
            "payment_request": payment_request,
            "payment_hash": payment_hash,
            "amount_sats": INVOICE_AMOUNT_SATS,
            "username": username,
            "pubkey": pubkey_hex
        }
    except httpx.RequestError as e:
        logger.error(f"LNbits connection error in create_invoice: {e}")
        raise HTTPException(status_code=500, detail="Connection error communicating with payment provider")


@app.post("/api/check-payment")
@limiter.limit("30/minute")
async def check_payment(request: Request, data: CheckPaymentRequest):
    if not LNURL or not LNKEY:
        raise HTTPException(status_code=500, detail="Lightning payment not configured")

    username = data.username.strip()
    pubkey_hex = convert_npub_to_hex(data.pubkey)
    payment_hash = data.payment_hash

    try:
        response = await http_client.get(
            f"{LNURL}/api/v1/payments/{payment_hash}",
            headers={"X-Api-Key": LNKEY},
        )
        if response.status_code != 200:
            return {"paid": False}

        payment_data = response.json()

        if payment_data.get("paid"):
            memo = payment_data.get("memo") or payment_data.get("description") or ""

            if memo:
                expected_memo = f"NIP-05: {username}@{DOMAIN}"
                if not memo.startswith("NIP-05:"):
                    logger.warning(f"Payment hash {payment_hash[:16]}... has unexpected memo: {memo}")
                    return {"paid": False}

                if memo != expected_memo:
                    logger.warning(f"Payment memo mismatch: expected '{expected_memo}', got '{memo}'")
                    return {"paid": False}
            else:
                logger.info(f"Payment hash {payment_hash[:16]}... has no memo, accepting (LNbits may not support memo in payment response)")

            success = check_and_add_nip05_entry(username, pubkey_hex)
            if success:
                await db_update_pago(payment_hash, en_nostr_json=True)
                return {"paid": True}
            return {"paid": False, "error": "Username already registered"}
        return {"paid": False}
    except httpx.RequestError as e:
        logger.error(f"LNbits connection error in check_payment: {e}")
        return {"paid": False}


@app.post("/api/register")
@limiter.limit("5/minute")
async def register_nip05(data: NIP05Request, request: Request):
    if not ADMIN_API_KEY:
        raise HTTPException(status_code=501, detail="Direct registration is disabled")

    provided_key = request.headers.get("X-Admin-Key")
    if not secrets.compare_digest(provided_key, ADMIN_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid admin API key")

    username = data.username.strip()
    pubkey_hex = convert_npub_to_hex(data.pubkey)

    if not check_and_add_nip05_entry(username, pubkey_hex):
        raise HTTPException(status_code=400, detail="This NIP-05 identifier is already in use")

    await db_insert_registro(
        nip05=f"{username}@{DOMAIN}",
        npub=data.pubkey,
        pubkey_hex=pubkey_hex,
        pago_completado=True,
        en_nostr_json=True,
    )

    return {"success": True, "nip05": f"{username}@{DOMAIN}"}


@app.get("/api/ultimos-registros")
@limiter.limit("30/minute")
async def ultimos_registros(request: Request):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT nip05, npub, pago_completado, en_nostr_json FROM registros ORDER BY id DESC LIMIT 5"
        )
        rows = await cursor.fetchall()
    return [
        {
            "nip05": row["nip05"],
            "npub": row["npub"],
            "en_nostr_json": bool(row["en_nostr_json"]),
            "pago_completado": bool(row["pago_completado"]),
        }
        for row in rows
    ]


@app.get("/api/check-availability/{username}")
@limiter.limit("30/minute")
async def check_availability(request: Request, username: str):
    if not re.match(r'^[a-zA-Z0-9_-]{1,30}$', username):
        raise HTTPException(status_code=400, detail="Invalid username format")
    available = check_nip05_available(username.strip())
    return {"available": available}


@app.post("/api/check-pubkey")
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


if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting NIP-05 Nostr Identifier server...")
    logger.info(f"Domain: {DOMAIN}")
    logger.info(f"Invoice amount: {INVOICE_AMOUNT_SATS} sats")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
    
    logger.info("Server stopped gracefully")
