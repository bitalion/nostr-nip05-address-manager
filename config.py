import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
WELL_KNOWN_DIR = BASE_DIR / ".well-known"
NOSTR_JSON_PATH = WELL_KNOWN_DIR / "nostr.json"
NOSTR_JSON_BACKUP = BASE_DIR / "nostr.json.bak"
DB_PATH = BASE_DIR / "base.sqlite"

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
    origins = []
    if DOMAIN != "example.com":
        origins.append(f"https://{DOMAIN}")
    origins.append("http://localhost")
    origins.append("http://localhost:8000")
    origins.append("http://127.0.0.1")
    origins.append("http://127.0.0.1:8000")
    ALLOWED_ORIGINS = origins

COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"
if DOMAIN in ("example.com", "localhost") or "localhost" in DOMAIN or "127.0.0.1" in DOMAIN:
    COOKIE_SECURE = False
