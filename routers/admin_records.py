import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import DOMAINS_MAP
from core.nostr import (
    _nostr_json_lock,
    check_and_add_nip05_entry,
    convert_npub_to_hex,
    load_nostr_json,
    save_nostr_json,
)
from core.security import get_current_user, require_role
from db.connection import get_db
from db.records import (
    db_create_admin_record,
    db_delete_record,
    db_update_record_pubkey,
    get_all_records,
)
from db.users import (
    create_user,
    delete_user,
    get_all_users,
    reset_user_password,
    update_user,
)
from schemas import (
    ManageRecordRequest,
    UserCreateRequest,
    UserResetPasswordRequest,
    UserUpdateRequest,
)

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)

router = APIRouter()


# ── Records ──────────────────────────────────────────────────────────────────

@router.get("/api/manage/records")
@limiter.limit("60/minute")
async def manage_get_records(request: Request, current_user: dict = Depends(get_current_user)):
    return await get_all_records()


@router.post("/api/manage/records")
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

    parts = data.nip05.split('@', 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise HTTPException(status_code=400, detail="NIP-05 must be in format user@domain")
    username, domain = parts
    if domain not in DOMAINS_MAP:
        raise HTTPException(status_code=400, detail=f"Domain not configured: {domain}")

    try:
        await db_create_admin_record(data.nip05, data.pubkey, pubkey_hex)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    added = await check_and_add_nip05_entry(username, pubkey_hex, domain)
    if not added:
        await db_delete_record(data.nip05)
        raise HTTPException(status_code=409, detail="NIP-05 already exists in nostr.json")
    return {"success": True}


@router.put("/api/manage/records")
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

    parts = data.nip05.split('@', 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise HTTPException(status_code=400, detail="NIP-05 must be in format user@domain")
    username, domain = parts

    success = await db_update_record_pubkey(data.nip05, data.pubkey, pubkey_hex)
    if not success:
        raise HTTPException(status_code=404, detail="Record not found")

    async with _nostr_json_lock:
        nostr_data = load_nostr_json()
        domain_names = nostr_data.get("domains", {}).get(domain, {})
        existing_key = next((k for k in domain_names if k.lower() == username.lower()), None)
        if existing_key:
            nostr_data["domains"][domain][existing_key] = pubkey_hex
            save_nostr_json(nostr_data)
        else:
            logger.warning(f"DB updated but nostr.json entry not found: {username}@{domain}")

    return {"success": True}


@router.delete("/api/manage/records/{record_id}")
@limiter.limit("30/minute")
async def manage_delete_record(request: Request, record_id: int, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    cursor = await db.execute("SELECT nip05 FROM records WHERE id = ?", (record_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Record not found")

    nip05 = row[0]
    parts = nip05.split('@', 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise HTTPException(status_code=500, detail="Stored NIP-05 is invalid")
    username, domain = parts

    async with _nostr_json_lock:
        nostr_data = load_nostr_json()
        domain_names = nostr_data.get("domains", {}).get(domain, {})
        existing_key = next((k for k in domain_names if k.lower() == username.lower()), None)
        if existing_key:
            del nostr_data["domains"][domain][existing_key]
            if not nostr_data["domains"][domain]:
                del nostr_data["domains"][domain]
            save_nostr_json(nostr_data)

    await db_delete_record(nip05)
    return {"success": True}


# ── Users ─────────────────────────────────────────────────────────────────────

@router.get("/api/manage/users")
@limiter.limit("30/minute")
async def manage_get_users(request: Request, current_user: dict = Depends(require_role("admin"))):
    return await get_all_users()


@router.post("/api/manage/users")
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


@router.put("/api/manage/users")
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


@router.delete("/api/manage/users/{user_id}")
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


@router.post("/api/manage/users/reset-password")
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
