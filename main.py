import logging
import os
import json
import re
import secrets
import tempfile
import shutil
import asyncio
import uuid
import time
import hashlib
import hmac
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from urllib.parse import urlparse
import aiosqlite
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
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
DB_PATH = BASE_DIR / "base.sqlite"

STATIC_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

LNURL = os.getenv("LNBITS_URL", "")
LNKEY = os.getenv("LNBITS_API_KEY", "")
INVOICE_AMOUNT_SATS = int(os.getenv("INVOICE_AMOUNT_SATS", "100"))
DOMAIN = os.getenv("DOMAIN", "example.com")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "noreply@example.com")

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "").split(",") if os.getenv("ALLOWED_ORIGINS") else []
if not ALLOWED_ORIGINS:
    ALLOWED_ORIGINS = [f"https://{DOMAIN}"] if DOMAIN != "example.com" else []

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
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; img-src 'self' data:; font-src 'self' https://cdnjs.cloudflare.com; connect-src 'self' https:; frame-ancestors 'none';"

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


_db_pool: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _db_pool
    if _db_pool is None:
        _db_pool = await aiosqlite.connect(DB_PATH)
        await _db_pool.execute("PRAGMA journal_mode=WAL")
        await _db_pool.execute("PRAGMA foreign_keys=ON")
    return _db_pool


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS records (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                nip05                TEXT    NOT NULL UNIQUE,
                npub                 TEXT    NOT NULL,
                pubkey_hex           TEXT    NOT NULL,
                payment_hash         TEXT,
                payment_completed    INTEGER NOT NULL DEFAULT 0,
                admin_only           INTEGER NOT NULL DEFAULT 0,
                registration_date    INTEGER NOT NULL,
                updated_at           INTEGER NOT NULL,
                in_nostr_json        INTEGER NOT NULL DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                username        TEXT    NOT NULL UNIQUE,
                password_hash   TEXT    NOT NULL,
                email           TEXT,
                role            TEXT    NOT NULL DEFAULT 'admin',
                created_at      INTEGER NOT NULL,
                last_login      INTEGER,
                is_active       INTEGER NOT NULL DEFAULT 1
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_nip05 ON records(nip05)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_npub ON records(pubkey_hex)")

        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        
        try:
            await db.execute("ALTER TABLE users ADD COLUMN email TEXT")
        except aiosqlite.OperationalError as e:
            if "duplicate column name" not in str(e):
                raise
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                token           TEXT    NOT NULL UNIQUE,
                expires_at      INTEGER NOT NULL,
                used            INTEGER NOT NULL DEFAULT 0,
                created_at      INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        hashed = hash_password("manage")
        await db.execute(
            """INSERT OR IGNORE INTO users (username, password_hash, role, created_at) 
               VALUES (?, ?, 'admin', ?)""",
            ("admin", hashed, int(time.time()))
        )
        
        await db.commit()
    logger.info(f"Database initialized at {DB_PATH}")


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return f"{salt}${pwd_hash.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt, pwd_hash = password_hash.split('$')
        return hmac.compare_digest(
            hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex(),
            pwd_hash
        )
    except ValueError:
        return False


def send_email(to_email: str, subject: str, body: str) -> bool:
    if not SMTP_HOST or not SMTP_USER:
        logger.warning("Email not configured, skipping send")
        return False
    
    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_FROM
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "html"))
        
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, to_email, msg.as_string())
        
        logger.info(f"Email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False


async def create_password_reset_token(username: str) -> tuple[str, int] | None:
    db = await get_db()
    db.row_factory = aiosqlite.Row
    
    cursor = await db.execute(
        "SELECT id, username FROM users WHERE LOWER(username) = ? AND is_active = 1",
        (username.lower(),)
    )
    row = await cursor.fetchone()
    if not row:
        return None
    
    token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + 3600
    
    await db.execute(
        """INSERT INTO password_reset_tokens (user_id, token, expires_at, created_at)
           VALUES (?, ?, ?, ?)""",
        (row["id"], token, expires_at, int(time.time()))
    )
    await db.commit()
    
    return token, expires_at


async def verify_password_reset_token(token: str) -> int | None:
    db = await get_db()
    db.row_factory = aiosqlite.Row
    
    cursor = await db.execute(
        """SELECT user_id FROM password_reset_tokens 
           WHERE token = ? AND used = 0 AND expires_at > ?""",
        (token, int(time.time()))
    )
    row = await cursor.fetchone()
    return row["user_id"] if row else None


async def use_password_reset_token(token: str) -> bool:
    db = await get_db()
    cursor = await db.execute(
        "UPDATE password_reset_tokens SET used = 1 WHERE token = ?",
        (token,)
    )
    await db.commit()
    return cursor.rowcount > 0


async def update_user_password(user_id: int, new_password: str) -> bool:
    db = await get_db()
    password_hash = hash_password(new_password)
    cursor = await db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (password_hash, user_id)
    )
    await db.commit()
    return cursor.rowcount > 0


async def get_all_users() -> list:
    db = await get_db()
    db.row_factory = aiosqlite.Row
    cursor = await db.execute(
        "SELECT id, username, email, role, created_at, last_login, is_active FROM users ORDER BY id DESC"
    )
    rows = await cursor.fetchall()
    return [
        {
            "id": row["id"],
            "username": row["username"],
            "email": row["email"],
            "role": row["role"],
            "created_at": row["created_at"],
            "last_login": row["last_login"],
            "is_active": bool(row["is_active"]),
        }
        for row in rows
    ]


async def get_user_by_id(user_id: int) -> dict | None:
    db = await get_db()
    db.row_factory = aiosqlite.Row
    cursor = await db.execute(
        "SELECT id, username, email, role, created_at, last_login, is_active FROM users WHERE id = ?",
        (user_id,)
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
        "role": row["role"],
        "created_at": row["created_at"],
        "last_login": row["last_login"],
        "is_active": bool(row["is_active"]),
    }


async def create_user(username: str, password: str, email: str | None, role: str) -> int:
    db = await get_db()
    password_hash = hash_password(password)
    timestamp = int(time.time())
    try:
        cursor = await db.execute(
            """INSERT INTO users (username, password_hash, email, role, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (username.lower(), password_hash, email, role, timestamp)
        )
        await db.commit()
        return cursor.lastrowid
    except aiosqlite.IntegrityError:
        raise ValueError(f"User {username} already exists")


async def update_user(user_id: int, email: str | None, role: str, is_active: bool) -> bool:
    db = await get_db()
    cursor = await db.execute(
        "UPDATE users SET email = ?, role = ?, is_active = ? WHERE id = ?",
        (email, role, 1 if is_active else 0, user_id)
    )
    await db.commit()
    return cursor.rowcount > 0


async def delete_user(user_id: int) -> bool:
    db = await get_db()
    cursor = await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    await db.commit()
    return cursor.rowcount > 0


async def reset_user_password(user_id: int, new_password: str) -> bool:
    db = await get_db()
    password_hash = hash_password(new_password)
    cursor = await db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (password_hash, user_id)
    )
    await db.commit()
    return cursor.rowcount > 0


async def authenticate_user(username: str, password: str) -> dict | None:
    db = await get_db()
    db.row_factory = aiosqlite.Row
    cursor = await db.execute(
        "SELECT * FROM users WHERE username = ? AND is_active = 1",
        (username.lower(),)
    )
    row = await cursor.fetchone()
    if not row:
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    await db.execute(
        "UPDATE users SET last_login = ? WHERE id = ?",
        (int(time.time()), row["id"])
    )
    await db.commit()
    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"]
    }


async def get_all_records() -> list:
    db = await get_db()
    db.row_factory = aiosqlite.Row
    cursor = await db.execute("SELECT * FROM records ORDER BY id DESC")
    rows = await cursor.fetchall()
    return [
        {
            "id": row["id"],
            "nip05": row["nip05"],
            "npub": row["npub"],
            "pubkey_hex": row["pubkey_hex"],
            "payment_hash": row["payment_hash"],
            "payment_completed": bool(row["payment_completed"]),
            "admin_only": bool(row["admin_only"]),
            "registration_date": row["registration_date"],
            "updated_at": row["updated_at"],
            "in_nostr_json": bool(row["in_nostr_json"]),
        }
        for row in rows
    ]


async def db_create_admin_record(
    nip05: str,
    npub: str,
    pubkey_hex: str,
) -> int:
    db = await get_db()
    timestamp = int(time.time())
    try:
        cursor = await db.execute(
            """INSERT INTO records
               (nip05, npub, pubkey_hex, payment_completed, admin_only, registration_date, updated_at, in_nostr_json)
               VALUES (?, ?, ?, 1, 1, ?, ?, 1)""",
            (nip05.lower(), npub, pubkey_hex, timestamp, timestamp),
        )
        await db.commit()
        logger.info(f"DB admin insert record id={cursor.lastrowid} nip05={nip05}")
        return cursor.lastrowid
    except aiosqlite.IntegrityError:
        logger.warning(f"Duplicate nip05 attempt: {nip05}")
        raise ValueError(f"NIP-05 {nip05} already exists")


async def db_insert_record(
    nip05: str,
    npub: str,
    pubkey_hex: str,
    payment_completed: bool = False,
    admin_only: bool = False,
    in_nostr_json: bool = False,
) -> int:
    db = await get_db()
    timestamp = int(time.time())
    try:
        cursor = await db.execute(
            """INSERT INTO records
               (nip05, npub, pubkey_hex, payment_completed, admin_only, registration_date, updated_at, in_nostr_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                nip05.lower(), npub, pubkey_hex,
                1 if payment_completed else 0,
                1 if admin_only else 0,
                timestamp,
                timestamp,
                1 if in_nostr_json else 0,
            ),
        )
        await db.commit()
        logger.info(f"DB insert record id={cursor.lastrowid} nip05={nip05}")
        return cursor.lastrowid
    except aiosqlite.IntegrityError:
        logger.warning(f"Duplicate nip05 attempt: {nip05}")
        raise ValueError(f"NIP-05 {nip05} already exists")


async def db_update_payment(payment_hash: str, in_nostr_json: bool = True) -> bool:
    db = await get_db()
    timestamp = int(time.time())
    cursor = await db.execute(
        "UPDATE records SET payment_completed = 1, in_nostr_json = ?, updated_at = ? WHERE payment_hash = ?",
        (1 if in_nostr_json else 0, timestamp, payment_hash),
    )
    await db.commit()
    if cursor.rowcount > 0:
        logger.info(f"DB payment updated payment_hash={payment_hash[:16]}… in_nostr_json={in_nostr_json}")
        return True
    logger.warning(f"Payment hash not found: {payment_hash[:16]}...")
    return False


async def db_insert_record_with_payment(
    nip05: str,
    npub: str,
    pubkey_hex: str,
    payment_hash: str,
) -> int:
    db = await get_db()
    timestamp = int(time.time())
    try:
        cursor = await db.execute(
            """INSERT INTO records
               (nip05, npub, pubkey_hex, payment_hash, payment_completed, admin_only, registration_date, updated_at, in_nostr_json)
               VALUES (?, ?, ?, ?, 0, 0, ?, ?, 0)""",
            (nip05.lower(), npub, pubkey_hex, payment_hash, timestamp, timestamp),
        )
        await db.commit()
        logger.info(f"DB insert record id={cursor.lastrowid} nip05={nip05}")
        return cursor.lastrowid
    except aiosqlite.IntegrityError:
        await db.rollback()
        logger.warning(f"Duplicate nip05 or payment_hash: {nip05}")
        raise ValueError(f"NIP-05 {nip05} or payment already exists")


async def db_delete_record(nip05: str) -> bool:
    db = await get_db()
    cursor = await db.execute("SELECT id FROM records WHERE LOWER(nip05) = ?", (nip05.lower(),))
    row = await cursor.fetchone()
    if not row:
        return False
    
    record_id = row[0]
    await db.execute("DELETE FROM records WHERE id = ?", (record_id,))
    await db.commit()
    logger.info(f"DB deleted record nip05={nip05}")
    return True


async def db_update_record_pubkey(nip05: str, new_npub: str, new_pubkey_hex: str) -> bool:
    db = await get_db()
    timestamp = int(time.time())
    cursor = await db.execute(
        """UPDATE records SET npub = ?, pubkey_hex = ?, updated_at = ? 
           WHERE LOWER(nip05) = ?""",
        (new_npub, new_pubkey_hex, timestamp, nip05.lower()),
    )
    await db.commit()
    success = cursor.rowcount > 0
    if success:
        logger.info(f"DB updated pubkey for nip05={nip05}")
    return success


async def db_update_nostr_json_status(nip05: str, in_nostr_json: bool) -> bool:
    db = await get_db()
    timestamp = int(time.time())
    cursor = await db.execute(
        """UPDATE records SET in_nostr_json = ?, updated_at = ?
           WHERE LOWER(nip05) = ?""",
        (1 if in_nostr_json else 0, timestamp, nip05.lower()),
    )
    await db.commit()
    success = cursor.rowcount > 0
    if success:
        logger.info(f"DB updated in_nostr_json={in_nostr_json} for nip05={nip05}")
    return success


async def db_get_nip05_by_payment_hash(payment_hash: str) -> str | None:
    """Return the nip05 that was registered with this payment_hash, or None."""
    db = await get_db()
    db.row_factory = aiosqlite.Row
    cursor = await db.execute(
        "SELECT nip05 FROM records WHERE payment_hash = ?",
        (payment_hash,)
    )
    row = await cursor.fetchone()
    return row["nip05"] if row else None


async def db_get_pending_record(nip05: str) -> dict | None:
    """Return pending record (payment_completed=0) for nip05, or None."""
    db = await get_db()
    db.row_factory = aiosqlite.Row
    cursor = await db.execute(
        """SELECT id, nip05, npub, pubkey_hex, payment_hash, payment_completed, in_nostr_json, admin_only, registration_date, updated_at 
           FROM records WHERE LOWER(nip05) = ? AND payment_completed = 0""",
        (nip05.lower(),)
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "nip05": row["nip05"],
        "npub": row["npub"],
        "pubkey_hex": row["pubkey_hex"],
        "payment_hash": row["payment_hash"],
        "payment_completed": bool(row["payment_completed"]),
        "in_nostr_json": bool(row["in_nostr_json"]),
        "admin_only": bool(row["admin_only"]),
        "registration_date": row["registration_date"],
        "updated_at": row["updated_at"],
    }


async def db_delete_record_by_id(record_id: int) -> bool:
    """Delete a record by its ID."""
    db = await get_db()
    cursor = await db.execute("DELETE FROM records WHERE id = ?", (record_id,))
    await db.commit()
    return cursor.rowcount > 0


async def get_payment_status_from_lnbits(payment_hash: str) -> dict | None:
    """Get payment status from LNbits. Returns: {paid: bool, pending: bool, expired: bool} or None on error."""
    if not LNURL or not LNKEY:
        return None
    try:
        response = await http_client.get(
            f"{LNURL}/api/v1/payments/{payment_hash}",
            headers={"X-Api-Key": LNKEY},
        )
        if response.status_code != 200:
            return None
        data = response.json()
        return {
            "paid": data.get("paid", False),
            "pending": data.get("pending", False),
            "expired": data.get("expired", False) if "expired" in data else False,
        }
    except Exception:
        return None


http_client: httpx.AsyncClient | None = None


def _validate_lnurl(url: str) -> None:
    """Validate LNBITS_URL to prevent SSRF via misconfigured env vars."""
    if not url:
        return
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"LNBITS_URL must use http or https scheme, got: {parsed.scheme!r}")
    if not parsed.netloc:
        raise ValueError("LNBITS_URL must include a valid host")


@app.on_event("startup")
async def startup() -> None:
    global http_client
    _validate_lnurl(LNURL)
    http_client = httpx.AsyncClient(timeout=30.0)
    await init_db()
    # Initialize nostr.json only after the DB is ready to avoid a partially
    # functional state if DB initialization fails
    if not NOSTR_JSON_PATH.exists():
        with open(NOSTR_JSON_PATH, "w") as f:
            json.dump({"names": {}}, f)


@app.on_event("shutdown")
async def shutdown() -> None:
    global http_client, _db_pool
    if http_client:
        await http_client.aclose()
    if _db_pool:
        await _db_pool.close()
        _db_pool = None


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


_nostr_json_lock = asyncio.Lock()


async def check_nip05_available(nip05: str) -> bool:
    nip05_lower = nip05.lower().strip()

    async with _nostr_json_lock:
        data = load_nostr_json()
        for existing_nip05 in data.get("names", {}).keys():
            if existing_nip05.lower() == nip05_lower:
                return False

    db = await get_db()
    cursor = await db.execute(
        "SELECT 1 FROM records WHERE LOWER(nip05) = ? AND payment_completed = 1",
        (nip05_lower,)
    )
    row = await cursor.fetchone()
    if row:
        return False

    return True


async def check_and_add_nip05_entry(username: str, pubkey_hex: str) -> bool:
    async with _nostr_json_lock:
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

    await db_update_nostr_json_status(f"{username}@{DOMAIN}", True)
    return True


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
    username: str = Field(max_length=30)
    pubkey: str = Field(max_length=200)


class ConvertPubkeyRequest(ValidatedPubkeyMixin, BaseModel):
    pubkey: str = Field(max_length=200)


class CheckPaymentRequest(ValidatedPubkeyMixin, ValidatedUsernameMixin, BaseModel):
    username: str = Field(max_length=30)
    pubkey: str = Field(max_length=200)
    payment_hash: str = Field(max_length=64)

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


@app.get("/favicon.ico")
async def favicon():
    from fastapi.responses import FileResponse
    return FileResponse(STATIC_DIR / "images/favicon.ico")


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

    nip05_full = f"{username}@{DOMAIN}"
    
    pending_record = await db_get_pending_record(nip05_full)
    
    if pending_record:
        existing_payment_hash = pending_record["payment_hash"]
        payment_status = await get_payment_status_from_lnbits(existing_payment_hash)
        
        if payment_status and payment_status.get("paid"):
            logger.info(f"Pending payment already paid for {nip05_full}")
            return {
                "payment_request": None,
                "payment_hash": existing_payment_hash,
                "amount_sats": INVOICE_AMOUNT_SATS,
                "username": username,
                "pubkey": pubkey_hex,
                "status": "already_paid",
                "message": "Payment already completed"
            }
        
        payment_request = await get_invoice_from_lnbits(existing_payment_hash)
        if payment_request:
            logger.info(f"Returning existing pending invoice for {nip05_full}")
            return {
                "payment_request": payment_request,
                "payment_hash": existing_payment_hash,
                "amount_sats": INVOICE_AMOUNT_SATS,
                "username": username,
                "pubkey": pubkey_hex,
                "status": "pending",
                "message": "Existing invoice - please complete payment"
            }
        
        logger.info(f"Existing invoice expired or unavailable for {nip05_full}, creating new one")
        await db_delete_record_by_id(pending_record["id"])

    try:
        response = await http_client.post(
            f"{LNURL}/api/v1/payments",
            headers={"X-Api-Key": LNKEY, "Content-Type": "application/json"},
            json={
                "out": False,
                "amount": INVOICE_AMOUNT_SATS,
                "memo": f"NIP-05: {username}@{DOMAIN}",
                "expiry": 300,
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

        try:
            await db_insert_record_with_payment(
                nip05=nip05_full,
                npub=data.pubkey,
                pubkey_hex=pubkey_hex,
                payment_hash=payment_hash,
            )
        except ValueError as ve:
            logger.warning(f"Record already exists: {ve}")
            return {
                "payment_request": payment_request,
                "payment_hash": payment_hash,
                "amount_sats": INVOICE_AMOUNT_SATS,
                "username": username,
                "pubkey": pubkey_hex,
                "status": "pending",
                "message": "Invoice pending payment"
            }

        return {
            "payment_request": payment_request,
            "payment_hash": payment_hash,
            "amount_sats": INVOICE_AMOUNT_SATS,
            "username": username,
            "pubkey": pubkey_hex,
            "status": "created",
            "message": "Invoice created"
        }
    except httpx.RequestError as e:
        logger.error(f"LNbits connection error in create_invoice: {e}")
        raise HTTPException(status_code=500, detail="Connection error communicating with payment provider")


async def get_invoice_from_lnbits(payment_hash: str) -> str | None:
    """Get the payment request (invoice) from LNbits for a given payment hash."""
    if not LNURL or not LNKEY:
        return None
    try:
        response = await http_client.get(
            f"{LNURL}/api/v1/payments/{payment_hash}",
            headers={"X-Api-Key": LNKEY},
        )
        if response.status_code != 200:
            return None
        data = response.json()
        return data.get("payment_request") or data.get("bolt11") or data.get("pr")
    except Exception:
        return None


class CancelRegistrationRequest(BaseModel):
    username: str = Field(max_length=50)


@app.post("/api/cancel-registration")
@limiter.limit("10/minute")
async def cancel_registration(request: Request, data: CancelRegistrationRequest):
    username = data.username.strip()
    nip05_full = f"{username}@{DOMAIN}"
    
    pending_record = await db_get_pending_record(nip05_full)
    if not pending_record:
        return {"success": False, "message": "No pending registration found"}
    
    await db_delete_record_by_id(pending_record["id"])
    logger.info(f"Cancelled pending registration for {nip05_full}")
    return {"success": True, "message": "Registration cancelled"}


@app.post("/api/check-payment")
@limiter.limit("30/minute")
async def check_payment(request: Request, data: CheckPaymentRequest):
    if not LNURL or not LNKEY:
        raise HTTPException(status_code=500, detail="Lightning payment not configured")

    username = data.username.strip()
    pubkey_hex = convert_npub_to_hex(data.pubkey)
    payment_hash = data.payment_hash

    # Verify the invoice was created for this exact username to prevent hijacking
    registered_nip05 = await db_get_nip05_by_payment_hash(payment_hash)
    expected_nip05 = f"{username}@{DOMAIN}"
    if registered_nip05 != expected_nip05:
        logger.warning(
            f"Payment hijack attempt: hash {payment_hash[:16]}... "
            f"belongs to {registered_nip05!r}, claimed by {expected_nip05!r}"
        )
        raise HTTPException(status_code=400, detail="Payment hash does not match this registration")

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

            if not await check_nip05_available(username):
                logger.warning(f"Payment verified but username {username} is already taken")
                return {"paid": False, "error": "Username already registered"}

            success = await check_and_add_nip05_entry(username, pubkey_hex)
            if success:
                await db_update_payment(payment_hash, in_nostr_json=True)
                return {"paid": True}
            return {"paid": False, "error": "Failed to register NIP-05"}
        return {"paid": False}
    except httpx.RequestError as e:
        logger.error(f"LNbits connection error in check_payment: {e}")
        return {"paid": False}


@app.post("/api/register")
@limiter.limit("5/minute")
async def register_nip05(data: NIP05Request, request: Request):
    if not ADMIN_API_KEY:
        raise HTTPException(status_code=501, detail="Direct registration is disabled")

    provided_key = request.headers.get("X-Admin-Key", "")
    if not provided_key or not secrets.compare_digest(provided_key, ADMIN_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid admin API key")

    username = data.username.strip()
    pubkey_hex = convert_npub_to_hex(data.pubkey)

    if not await check_and_add_nip05_entry(username, pubkey_hex):
        raise HTTPException(status_code=400, detail="This NIP-05 identifier is already in use")

    await db_insert_record(
        nip05=f"{username}@{DOMAIN}",
        npub=data.pubkey,
        pubkey_hex=pubkey_hex,
        payment_completed=True,
        admin_only=True,
        in_nostr_json=True,
    )

    return {"success": True, "nip05": f"{username}@{DOMAIN}"}


@app.get("/api/latest-records")
@limiter.limit("30/minute")
async def latest_records(request: Request):
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
            if len(username) <= 3:
                protected_nip05 = f"***@{parts[1]}"
            else:
                protected_nip05 = f"***{username[3:]}@{parts[1]}"
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


@app.get("/api/check-availability/{username}")
@limiter.limit("30/minute")
async def check_availability(request: Request, username: str):
    if not re.match(r'^[a-zA-Z0-9_-]{1,30}$', username):
        raise HTTPException(status_code=400, detail="Invalid username format")
    available = await check_nip05_available(username.strip())
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


class LoginRequest(BaseModel):
    username: str = Field(max_length=50)
    password: str = Field(max_length=200)


class ManageRecordRequest(BaseModel):
    nip05: str = Field(max_length=100)
    pubkey: str = Field(max_length=200)
    id: int | None = None


_http_bearer = HTTPBearer()


async def verify_token(token: str) -> dict | None:
    try:
        import base64
        decoded = base64.b64decode(token).decode()
        user_id, username = decoded.split(":")
        user_id = int(user_id)
    except Exception:
        return None
    
    db = await get_db()
    db.row_factory = aiosqlite.Row
    cursor = await db.execute(
        "SELECT id, username, role FROM users WHERE id = ? AND is_active = 1",
        (user_id,)
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return {"id": row["id"], "username": row["username"], "role": row["role"]}


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(_http_bearer)) -> dict:
    user = await verify_token(credentials.credentials)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


def require_role(required_role: str):
    async def role_checker(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("role") != required_role and current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return role_checker


@app.get("/manage", response_class=HTMLResponse)
async def manage_page(request: Request):
    return templates.TemplateResponse("manage.html", {"request": request, "domain": DOMAIN})


@app.post("/api/manage/login")
@limiter.limit("5/minute")
async def manage_login(request: Request, data: LoginRequest):
    user = await authenticate_user(data.username, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    import base64
    token = base64.b64encode(f"{user['id']}:{user['username']}".encode()).decode()
    return {"token": token, "user": user}


@app.post("/api/manage/logout")
async def manage_logout():
    return {"success": True}


class PasswordResetRequest(BaseModel):
    username: str = Field(max_length=50)


class PasswordResetConfirm(BaseModel):
    token: str = Field(max_length=100)
    new_password: str = Field(max_length=200)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


@app.post("/api/manage/password-reset")
@limiter.limit("3/minute")
async def request_password_reset(request: Request, data: PasswordResetRequest):
    if not SMTP_HOST:
        raise HTTPException(status_code=503, detail="Password reset not available")
    
    result = await create_password_reset_token(data.username)
    if not result:
        return {"message": "If the user exists, a reset email will be sent"}
    
    token, expires_at = result
    
    reset_url = f"https://{DOMAIN}/manage/reset?token={token}"
    
    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background: #08080f; color: white; padding: 20px;">
        <div style="max-width: 400px; margin: 0 auto; background: rgba(255,255,255,0.05); padding: 30px; border-radius: 15px;">
            <h2 style="text-align: center;">Password Reset</h2>
            <p>Click the button below to reset your password:</p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{reset_url}" style="background: #9333ea; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; display: inline-block;">Reset Password</a>
            </div>
            <p style="font-size: 12px; color: #888;">This link expires in 1 hour.</p>
        </div>
    </body>
    </html>
    """
    
    send_email(f"{data.username}@{DOMAIN}", "Password Reset Request", body)
    
    return {"message": "If the user exists, a reset email will be sent"}


@app.post("/api/manage/password-reset/confirm")
@limiter.limit("5/minute")
async def confirm_password_reset(request: Request, data: PasswordResetConfirm):
    user_id = await verify_password_reset_token(data.token)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    
    await update_user_password(user_id, data.new_password)
    await use_password_reset_token(data.token)
    
    return {"message": "Password updated successfully"}


@app.post("/api/manage/change-password")
@limiter.limit("5/minute")
async def change_password(
    request: Request,
    data: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
):
    user = await authenticate_user(current_user["username"], data.old_password)
    if not user:
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    await update_user_password(current_user["id"], data.new_password)

    return {"message": "Password updated successfully"}


class ProfileUpdateRequest(BaseModel):
    email: str | None = None


async def get_user_profile(user_id: int) -> dict | None:
    db = await get_db()
    db.row_factory = aiosqlite.Row
    cursor = await db.execute(
        "SELECT id, username, email, role, created_at, last_login FROM users WHERE id = ?",
        (user_id,)
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
        "role": row["role"],
        "created_at": row["created_at"],
        "last_login": row["last_login"],
    }


async def update_user_profile(user_id: int, email: str | None) -> bool:
    db = await get_db()
    cursor = await db.execute(
        "UPDATE users SET email = ? WHERE id = ?",
        (email, user_id)
    )
    await db.commit()
    return cursor.rowcount > 0


@app.get("/api/manage/profile")
@limiter.limit("30/minute")
async def manage_get_profile(request: Request, current_user: dict = Depends(get_current_user)):
    profile = await get_user_profile(current_user["id"])
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    return profile


@app.put("/api/manage/profile")
@limiter.limit("30/minute")
async def manage_update_profile(
    request: Request,
    data: ProfileUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    success = await update_user_profile(current_user["id"], data.email)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "Profile updated successfully", "email": data.email}


class UserCreateRequest(BaseModel):
    username: str = Field(max_length=50)
    password: str = Field(max_length=200)
    email: str | None = None
    role: str = Field(max_length=20)


class UserUpdateRequest(BaseModel):
    id: int
    email: str | None = None
    role: str = Field(max_length=20)
    is_active: bool


class UserResetPasswordRequest(BaseModel):
    user_id: int
    new_password: str = Field(max_length=200)


@app.get("/api/manage/users")
@limiter.limit("30/minute")
async def manage_get_users(request: Request, current_user: dict = Depends(require_role("admin"))):
    users = await get_all_users()
    return users


@app.post("/api/manage/users")
@limiter.limit("20/minute")
async def manage_create_user(
    request: Request,
    data: UserCreateRequest,
    current_user: dict = Depends(require_role("admin")),
):
    if data.role not in ("admin", "operator"):
        raise HTTPException(status_code=400, detail="Invalid role")
    try:
        user_id = await create_user(data.username, data.password, data.email, data.role)
        return {"success": True, "id": user_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/manage/users")
@limiter.limit("30/minute")
async def manage_update_user(
    request: Request,
    data: UserUpdateRequest,
    current_user: dict = Depends(require_role("admin")),
):
    if data.role not in ("admin", "operator"):
        raise HTTPException(status_code=400, detail="Invalid role")
    success = await update_user(data.id, data.email, data.role, data.is_active)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"success": True}


@app.delete("/api/manage/users/{user_id}")
@limiter.limit("30/minute")
async def manage_delete_user(
    request: Request,
    user_id: int,
    current_user: dict = Depends(require_role("admin")),
):
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    success = await delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"success": True}


@app.post("/api/manage/users/reset-password")
@limiter.limit("20/minute")
async def manage_reset_user_password(
    request: Request,
    data: UserResetPasswordRequest,
    current_user: dict = Depends(require_role("admin")),
):
    success = await reset_user_password(data.user_id, data.new_password)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"success": True}


@app.get("/api/manage/records")
@limiter.limit("60/minute")
async def manage_get_records(request: Request, current_user: dict = Depends(get_current_user)):
    records = await get_all_records()
    return records


@app.post("/api/manage/records")
@limiter.limit("30/minute")
async def manage_create_record(
    request: Request,
    data: ManageRecordRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        pubkey_hex = convert_npub_to_hex(data.pubkey)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await db_create_admin_record(data.nip05, data.pubkey, pubkey_hex)
    await check_and_add_nip05_entry(data.nip05.split('@')[0], pubkey_hex)

    return {"success": True}


@app.put("/api/manage/records")
@limiter.limit("30/minute")
async def manage_update_record(
    request: Request,
    data: ManageRecordRequest,
    current_user: dict = Depends(get_current_user),
):
    if not data.id:
        raise HTTPException(status_code=400, detail="Record ID required")

    try:
        pubkey_hex = convert_npub_to_hex(data.pubkey)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    success = await db_update_record_pubkey(data.nip05, data.pubkey, pubkey_hex)
    if not success:
        raise HTTPException(status_code=404, detail="Record not found")

    username = data.nip05.split('@')[0]
    async with _nostr_json_lock:
        data_json = load_nostr_json()
        if "names" in data_json and username in data_json["names"]:
            data_json["names"][username] = pubkey_hex
            save_nostr_json(data_json)

    return {"success": True}


@app.delete("/api/manage/records/{record_id}")
@limiter.limit("30/minute")
async def manage_delete_record(
    request: Request,
    record_id: int,
):
    db = await get_db()
    cursor = await db.execute("SELECT nip05 FROM records WHERE id = ?", (record_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Record not found")
    
    nip05 = row[0]
    username = nip05.split('@')[0]
    
    async with _nostr_json_lock:
        data_json = load_nostr_json()
        if "names" in data_json and username in data_json["names"]:
            del data_json["names"][username]
            save_nostr_json(data_json)
    
    await db_delete_record(nip05)
    
    return {"success": True}


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
