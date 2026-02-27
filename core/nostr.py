import asyncio
import json
import logging
import os
import re
import shutil
import tempfile
import time
import bech32
from config import DOMAIN, NOSTR_JSON_PATH, NOSTR_JSON_BACKUP

logger = logging.getLogger(__name__)

_nostr_json_lock = asyncio.Lock()


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
            except (json.JSONDecodeError, OSError):
                logger.error("Backup is also corrupt")
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
        with tempfile.NamedTemporaryFile(
            mode='w', dir=NOSTR_JSON_PATH.parent, delete=False, suffix='.tmp.json'
        ) as tmp:
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


async def check_nip05_available(nip05: str) -> bool:
    from db.connection import get_db
    from config import DOMAIN
    nip05_lower = nip05.lower().strip()
    nip05_full = f"{nip05_lower}@{DOMAIN}"

    async with _nostr_json_lock:
        data = load_nostr_json()
        for existing in data.get("names", {}).keys():
            if existing.lower() == nip05_lower:
                return False

    db = await get_db()
    cursor = await db.execute(
        "SELECT 1 FROM records WHERE LOWER(nip05) = ?",
        (nip05_full.lower(),)
    )
    row = await cursor.fetchone()
    return row is None


async def check_and_add_nip05_entry(username: str, pubkey_hex: str) -> bool:
    from db.records import db_update_nostr_json_status
    async with _nostr_json_lock:
        data = load_nostr_json()
        if "names" not in data:
            data["names"] = {}

        username_lower = username.lower().strip()
        for existing in data.get("names", {}).keys():
            if existing.lower() == username_lower:
                return False

        data["names"][username] = pubkey_hex
        save_nostr_json(data)
        logger.info(f"Added NIP-05 entry for user: {username}")

    await db_update_nostr_json_status(f"{username}@{DOMAIN}", True)
    return True


async def check_and_add_nip05_entry_atomic(username: str, pubkey_hex: str, payment_hash: str) -> bool:
    """Atomically verify username availability, write nostr.json, and confirm payment in DB.

    All three operations happen inside a single lock acquisition to eliminate the race
    condition between availability check, file write, and DB update.
    """
    from db.connection import get_db
    async with _nostr_json_lock:
        data = load_nostr_json()
        if "names" not in data:
            data["names"] = {}

        username_lower = username.lower().strip()
        for existing in data.get("names", {}).keys():
            if existing.lower() == username_lower:
                return False

        data["names"][username] = pubkey_hex
        save_nostr_json(data)

        db = await get_db()
        ts = int(time.time())
        await db.execute(
            "UPDATE records SET payment_completed=1, in_nostr_json=1, updated_at=? WHERE payment_hash=?",
            (ts, payment_hash)
        )
        await db.commit()

    logger.info(f"Atomic NIP-05 add + payment confirm for user: {username}")
    return True
