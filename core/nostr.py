import asyncio
import json
import logging
import os
import re
import shutil
import tempfile
import time
import bech32
from config import get_nostr_json_path, get_nostr_json_backup, PRIMARY_DOMAIN, NOSTR_DATA_DIR, _LEGACY_NOSTR_JSON

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


def _atomic_write_json(path, data):
    """Write JSON atomically using temp file + fsync + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', dir=path.parent, delete=False, suffix='.tmp.json'
        ) as tmp:
            json.dump(data, tmp, indent=2)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = tmp.name
        shutil.move(tmp_path, path)
        os.chmod(path, 0o644)
    except Exception:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def load_nostr_json(domain: str) -> dict:
    nostr_json_path = get_nostr_json_path(domain)
    backup_path = get_nostr_json_backup(domain)
    try:
        with open(nostr_json_path, "r") as f:
            data = json.load(f)
            count = len(data.get("names", {}))
            logger.info(f"Loaded nostr.json for {domain} with {count} entries")
            return data
    except FileNotFoundError:
        logger.warning(f"nostr.json not found for {domain} at {nostr_json_path}")
    except json.JSONDecodeError as e:
        logger.error(f"nostr.json for {domain} is corrupt: invalid JSON at position {e.pos}")
        if backup_path.exists():
            try:
                with open(backup_path, "r") as f:
                    data = json.load(f)
                count = len(data.get("names", {}))
                logger.info(f"Recovered {count} entries from backup for {domain}")
                return data
            except (json.JSONDecodeError, OSError):
                logger.error(f"Backup for {domain} is also corrupt")
    except OSError as e:
        logger.error(f"Error reading nostr.json for {domain}: {e.filename or 'unknown file'}")
    return {"names": {}}


def save_nostr_json(data: dict, domain: str) -> None:
    if not isinstance(data.get("names"), dict):
        raise ValueError("Invalid nostr.json structure: 'names' must be a dict")

    nostr_json_path = get_nostr_json_path(domain)
    backup_path = get_nostr_json_backup(domain)

    if nostr_json_path.exists():
        shutil.copy2(nostr_json_path, backup_path)

    _atomic_write_json(nostr_json_path, data)
    count = len(data["names"])
    logger.info(f"Saved nostr.json for {domain} with {count} entries")


def migrate_to_per_domain():
    """One-time migration: split centralized nostr.json into per-domain files."""
    if not _LEGACY_NOSTR_JSON.exists():
        return

    try:
        with open(_LEGACY_NOSTR_JSON, "r") as f:
            legacy_data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Cannot read legacy nostr.json for migration: {e}")
        return

    # Detect format: {"domains": {...}} or {"names": {...}}
    if "domains" in legacy_data:
        domains_dict = legacy_data["domains"]
    elif "names" in legacy_data:
        domains_dict = {PRIMARY_DOMAIN: legacy_data["names"]}
    else:
        logger.warning("Legacy nostr.json has unknown format, skipping migration")
        return

    for domain, names in domains_dict.items():
        if not names:
            continue
        nostr_json_path = get_nostr_json_path(domain)
        # Merge if destination already exists
        if nostr_json_path.exists():
            try:
                with open(nostr_json_path, "r") as f:
                    existing = json.load(f)
                existing_names = existing.get("names", {})
            except (json.JSONDecodeError, OSError):
                existing_names = {}
        else:
            existing_names = {}

        merged = {**existing_names, **names}
        _atomic_write_json(nostr_json_path, {"names": merged})
        logger.info(f"Migrated {len(names)} entries to {domain} (total: {len(merged)})")

    # Rename legacy file
    migrated_path = _LEGACY_NOSTR_JSON.with_suffix(".json.migrated")
    _LEGACY_NOSTR_JSON.rename(migrated_path)
    logger.info(f"Legacy nostr.json renamed to {migrated_path}")


async def check_nip05_available(nip05: str, domain: str) -> bool:
    from db.connection import get_db
    nip05_lower = nip05.lower().strip()
    nip05_full = f"{nip05_lower}@{domain}"

    async with _nostr_json_lock:
        data = load_nostr_json(domain)
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


async def check_and_add_nip05_entry(username: str, pubkey_hex: str, domain: str) -> bool:
    from db.records import db_update_nostr_json_status
    async with _nostr_json_lock:
        data = load_nostr_json(domain)
        if "names" not in data:
            data["names"] = {}

        username_lower = username.lower().strip()
        for existing in data["names"].keys():
            if existing.lower() == username_lower:
                return False

        data["names"][username] = pubkey_hex
        save_nostr_json(data, domain)
        logger.info(f"Added NIP-05 entry for user: {username}@{domain}")

    await db_update_nostr_json_status(f"{username}@{domain}", True)
    return True


async def check_and_add_nip05_entry_atomic(username: str, pubkey_hex: str, payment_hash: str, domain: str) -> bool:
    """Atomically verify username availability, write nostr.json, and confirm payment in DB.

    All three operations happen inside a single lock acquisition to eliminate the race
    condition between availability check, file write, and DB update.

    If writing nostr.json fails, DB is rolled back to maintain consistency.
    """
    from db.connection import get_db
    async with _nostr_json_lock:
        data = load_nostr_json(domain)
        if "names" not in data:
            data["names"] = {}

        username_lower = username.lower().strip()
        for existing in data["names"].keys():
            if existing.lower() == username_lower:
                return False

        db = await get_db()
        ts = int(time.time())
        await db.execute(
            "UPDATE records SET payment_completed=1, in_nostr_json=1, updated_at=? WHERE payment_hash=?",
            (ts, payment_hash)
        )

        data["names"][username] = pubkey_hex
        try:
            save_nostr_json(data, domain)
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to write nostr.json, rolled back DB: {e}")
            raise

        await db.commit()

    logger.info(f"Atomic NIP-05 add + payment confirm for user: {username}@{domain}")
    return True
