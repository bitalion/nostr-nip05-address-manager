import logging
import time
import aiosqlite
from db.connection import get_db

logger = logging.getLogger(__name__)


async def get_all_records(limit: int = 12, offset: int = 0) -> tuple[list, int]:
    db = await get_db()
    db.row_factory = aiosqlite.Row
    
    count_cursor = await db.execute("SELECT COUNT(*) as total FROM records")
    total = (await count_cursor.fetchone())["total"]
    
    cursor = await db.execute(
        "SELECT * FROM records ORDER BY id DESC LIMIT ? OFFSET ?",
        (limit, offset)
    )
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
    ], total


async def db_create_admin_record(nip05: str, npub: str, pubkey_hex: str) -> int:
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
                timestamp, timestamp,
                1 if in_nostr_json else 0,
            ),
        )
        await db.commit()
        logger.info(f"DB insert record id={cursor.lastrowid} nip05={nip05}")
        return cursor.lastrowid
    except aiosqlite.IntegrityError:
        logger.warning(f"Duplicate nip05 attempt: {nip05}")
        raise ValueError(f"NIP-05 {nip05} already exists")


async def db_insert_record_with_payment(
    nip05: str, npub: str, pubkey_hex: str, payment_hash: str
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


async def db_delete_record(nip05: str) -> bool:
    db = await get_db()
    cursor = await db.execute("SELECT id FROM records WHERE LOWER(nip05) = ?", (nip05.lower(),))
    row = await cursor.fetchone()
    if not row:
        return False
    await db.execute("DELETE FROM records WHERE id = ?", (row[0],))
    await db.commit()
    logger.info(f"DB deleted record nip05={nip05}")
    return True


async def db_delete_record_by_id(record_id: int) -> bool:
    db = await get_db()
    cursor = await db.execute("DELETE FROM records WHERE id = ?", (record_id,))
    await db.commit()
    return cursor.rowcount > 0


async def db_update_record_pubkey(nip05: str, new_npub: str, new_pubkey_hex: str) -> bool:
    db = await get_db()
    timestamp = int(time.time())
    cursor = await db.execute(
        "UPDATE records SET npub = ?, pubkey_hex = ?, updated_at = ? WHERE LOWER(nip05) = ?",
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
        "UPDATE records SET in_nostr_json = ?, updated_at = ? WHERE LOWER(nip05) = ?",
        (1 if in_nostr_json else 0, timestamp, nip05.lower()),
    )
    await db.commit()
    success = cursor.rowcount > 0
    if success:
        logger.info(f"DB updated in_nostr_json={in_nostr_json} for nip05={nip05}")
    return success


async def db_get_nip05_by_payment_hash(payment_hash: str) -> str | None:
    db = await get_db()
    db.row_factory = aiosqlite.Row
    cursor = await db.execute(
        "SELECT nip05 FROM records WHERE payment_hash = ?", (payment_hash,)
    )
    row = await cursor.fetchone()
    return row["nip05"] if row else None


async def db_get_pending_record(nip05: str) -> dict | None:
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
