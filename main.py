import os
import json
import re
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, validator
import bech32
import httpx

load_dotenv()

app = FastAPI(title="NIP-05 Nostr Identifier")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
WELL_KNOWN_DIR = BASE_DIR / ".well-known"
NOSTR_JSON_PATH = WELL_KNOWN_DIR / "nostr.json"

# Create static directory if it does not exist
STATIC_DIR.mkdir(exist_ok=True)

# Mount static files directory
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

LNURL = os.getenv("LNBITS_URL", "")
LNKEY = os.getenv("LNBITS_API_KEY", "")
INVOICE_AMOUNT_SATS = int(os.getenv("INVOICE_AMOUNT_SATS", "100"))
DOMAIN = os.getenv("DOMAIN", "example.com")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

WELL_KNOWN_DIR.mkdir(exist_ok=True)

if not NOSTR_JSON_PATH.exists():
    with open(NOSTR_JSON_PATH, "w") as f:
        json.dump({}, f)


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


def load_nostr_json() -> dict:
    try:
        with open(NOSTR_JSON_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def save_nostr_json(data: dict) -> None:
    with open(NOSTR_JSON_PATH, "w") as f:
        json.dump(data, f, indent=2)


def check_nip05_available(nip05: str) -> bool:
    data = load_nostr_json()
    nip05_lower = nip05.lower().strip()
    for existing_nip05 in data.get("names", {}).keys():
        if existing_nip05.lower() == nip05_lower:
            return False
    return True


class NIP05Request(BaseModel):
    username: str
    pubkey: str

    @validator('username')
    def validate_username(cls, v):
        if not re.match(r'^[a-zA-Z0-9_-]{1,30}$', v):
            raise ValueError('Username must be 1-30 characters, letters, numbers, underscores or hyphens only')
        return v

    @validator('pubkey')
    def validate_pubkey(cls, v):
        try:
            convert_npub_to_hex(v)
        except ValueError as e:
            raise ValueError(str(e))
        return v


class ConvertPubkeyRequest(BaseModel):
    pubkey: str

    @validator('pubkey')
    def validate_pubkey(cls, v):
        try:
            convert_npub_to_hex(v)
        except ValueError as e:
            raise ValueError(str(e))
        return v


class CheckPaymentRequest(BaseModel):
    username: str
    pubkey: str
    payment_hash: str

    @validator('username')
    def validate_username(cls, v):
        if not re.match(r'^[a-zA-Z0-9_-]{1,30}$', v):
            raise ValueError('Username must be 1-30 characters, letters, numbers, underscores or hyphens only')
        return v

    @validator('pubkey')
    def validate_pubkey(cls, v):
        try:
            convert_npub_to_hex(v)
        except ValueError as e:
            raise ValueError(str(e))
        return v


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    try:
        return templates.TemplateResponse("index.html", {"request": request, "domain": DOMAIN, "price_sats": INVOICE_AMOUNT_SATS})
    except Exception as e:
        return HTMLResponse(content=f"Error: {str(e)}", status_code=500)


@app.get("/.well-known/nostr.json")
async def get_nostr_json():
    return JSONResponse(content=load_nostr_json())


@app.post("/api/convert-pubkey")
async def convert_pubkey(data: ConvertPubkeyRequest):
    """Converts a pubkey (npub or hex) to hexadecimal format"""
    try:
        hex_key = convert_npub_to_hex(data.pubkey)
        return {"hex": hex_key}
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


if DEBUG:
    @app.get("/api/debug/lnbits-test")
    async def debug_lnbits_test():
        """Test endpoint to verify connectivity with LN Bits"""
        if not LNURL or not LNKEY:
            return {"error": "Lightning payment not configured"}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{LNURL}/api/v1/payments",
                    headers={"X-Api-Key": LNKEY, "Content-Type": "application/json"},
                    json={
                        "out": False,
                        "amount": 1,
                        "memo": "Debug test",
                    },
                    timeout=30.0
                )
                return {
                    "status_code": response.status_code,
                    "response": response.json() if response.status_code in (200, 201) else response.text
                }
            except Exception as e:
                return {"error": str(e)}


@app.post("/api/create-invoice")
async def create_invoice(data: NIP05Request):
    try:
        username = data.username.strip()
        pubkey_hex = convert_npub_to_hex(data.pubkey)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not check_nip05_available(username):
        raise HTTPException(status_code=400, detail="This NIP-05 identifier is already in use")

    if not LNURL or not LNKEY:
        raise HTTPException(status_code=500, detail="Lightning payment not configured")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{LNURL}/api/v1/payments",
                headers={"X-Api-Key": LNKEY, "Content-Type": "application/json"},
                json={
                    "out": False,
                    "amount": INVOICE_AMOUNT_SATS,
                    "memo": f"NIP-05: {username}@{DOMAIN}",
                },
                timeout=30.0
            )
            if response.status_code not in (200, 201):
                raise HTTPException(status_code=500, detail=f"Failed to create invoice: {response.status_code} {response.text}")

            invoice_data = response.json()
            print(f"DEBUG - LN Bits response: {invoice_data}")

            # Search for payment_request in multiple possible field names
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

            return {
                "payment_request": payment_request,
                "payment_hash": payment_hash,
                "amount_sats": INVOICE_AMOUNT_SATS,
                "username": username,
                "pubkey": pubkey_hex
            }
        except httpx.RequestError as e:
            raise HTTPException(status_code=500, detail=f"Connection error: {str(e)}")


@app.post("/api/check-payment")
async def check_payment(data: CheckPaymentRequest):
    if not LNURL or not LNKEY:
        raise HTTPException(status_code=500, detail="Lightning payment not configured")

    username = data.username.strip()
    pubkey_hex = convert_npub_to_hex(data.pubkey)
    payment_hash = data.payment_hash

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{LNURL}/api/v1/payments/{payment_hash}",
                headers={"X-Api-Key": LNKEY},
                timeout=30.0
            )
            if response.status_code != 200:
                return {"paid": False}

            payment_data = response.json()
            if payment_data.get("paid"):
                nip05_data = load_nostr_json()
                if "names" not in nip05_data:
                    nip05_data["names"] = {}
                nip05_data["names"][username] = pubkey_hex
                save_nostr_json(nip05_data)
                return {"paid": True}
            return {"paid": False}
        except httpx.RequestError:
            return {"paid": False}


@app.post("/api/register")
async def register_nip05(data: NIP05Request, request: Request):
    if not ADMIN_API_KEY:
        raise HTTPException(status_code=501, detail="Direct registration is disabled")

    provided_key = request.headers.get("X-Admin-Key")
    if provided_key != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid admin API key")

    username = data.username.strip()
    pubkey_hex = convert_npub_to_hex(data.pubkey)

    if not check_nip05_available(username):
        raise HTTPException(status_code=400, detail="This NIP-05 identifier is already in use")

    data_json = load_nostr_json()
    if "names" not in data_json:
        data_json["names"] = {}
    data_json["names"][username] = pubkey_hex
    save_nostr_json(data_json)

    return {"success": True, "nip05": f"{username}@{DOMAIN}"}


@app.get("/api/check-availability/{username}")
async def check_availability(username: str):
    available = check_nip05_available(username.strip())
    return {"available": available}


@app.post("/api/check-pubkey")
async def check_pubkey(data: ConvertPubkeyRequest):
    """Checks if a pubkey is already registered in nostr.json"""
    try:
        hex_key = convert_npub_to_hex(data.pubkey)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    nostr_data = load_nostr_json()
    for existing_hex in nostr_data.get("names", {}).values():
        if existing_hex.lower() == hex_key.lower():
            return {"hex": hex_key, "registered": True}
    return {"hex": hex_key, "registered": False}
