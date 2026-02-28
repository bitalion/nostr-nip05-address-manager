import logging
import secrets
import httpx
from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import ADMIN_API_KEY, DOMAINS_MAP, LNKEY, LNURL
from core.nostr import check_and_add_nip05_entry, check_and_add_nip05_entry_atomic, check_nip05_available, convert_npub_to_hex
from db.records import (
    db_delete_record_by_id,
    db_get_nip05_by_payment_hash,
    db_get_pending_record,
    db_insert_record,
    db_insert_record_with_payment,
)
from schemas import CancelRegistrationRequest, CheckPaymentRequest, NIP05Request
import services.payments as payments_svc

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)

router = APIRouter()


@router.post("/api/create-invoice")
@limiter.limit("10/minute")
async def create_invoice(request: Request, data: NIP05Request):
    try:
        username = data.username.strip()
        pubkey_hex = convert_npub_to_hex(data.pubkey)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    domain = data.domain
    price = DOMAINS_MAP[domain]

    if not LNURL or not LNKEY:
        raise HTTPException(status_code=500, detail="Lightning payment not configured")

    nip05_full = f"{username}@{domain}"
    pending_record = await db_get_pending_record(nip05_full)

    if pending_record:
        existing_hash = pending_record["payment_hash"]
        payment_status = await payments_svc.get_payment_status_from_lnbits(existing_hash)

        if payment_status and payment_status.get("paid"):
            return {
                "payment_request": None,
                "payment_hash": existing_hash,
                "amount_sats": price,
                "username": username,
                "pubkey": pubkey_hex,
                "status": "already_paid",
                "message": "Payment already completed",
            }

        payment_request = await payments_svc.get_invoice_from_lnbits(existing_hash)
        if payment_request:
            return {
                "payment_request": payment_request,
                "payment_hash": existing_hash,
                "amount_sats": price,
                "username": username,
                "pubkey": pubkey_hex,
                "status": "pending",
                "message": "Existing invoice - please complete payment",
            }

        logger.info(f"Existing invoice expired for {nip05_full}, creating new one")
        await db_delete_record_by_id(pending_record["id"])

    try:
        response = await payments_svc.http_client.post(
            f"{LNURL}/api/v1/payments",
            headers={"X-Api-Key": LNKEY, "Content-Type": "application/json"},
            json={
                "out": False,
                "amount": price,
                "memo": f"NIP-05: {username}@{domain}",
                "expiry": 300,
            },
        )
        if response.status_code not in (200, 201):
            logger.error(f"LNbits invoice creation failed: status={response.status_code}")
            raise HTTPException(status_code=500, detail="Failed to create invoice")

        invoice_data = response.json()
        payment_request = (
            invoice_data.get("payment_request")
            or invoice_data.get("bolt11")
            or invoice_data.get("pr")
        )
        payment_hash = (
            invoice_data.get("payment_hash")
            or invoice_data.get("checking_id")
            or invoice_data.get("id")
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
            "amount_sats": price,
            "username": username,
            "pubkey": pubkey_hex,
            "status": "created",
            "message": "Invoice created",
        }
    except httpx.RequestError as e:
        logger.error(f"LNbits connection error in create_invoice: {e}")
        raise HTTPException(status_code=500, detail="Connection error communicating with payment provider")


@router.post("/api/cancel-registration")
@limiter.limit("10/minute")
async def cancel_registration(request: Request, data: CancelRegistrationRequest):
    username = data.username.strip()
    domain = data.domain
    nip05_full = f"{username}@{domain}"

    pending_record = await db_get_pending_record(nip05_full)
    if not pending_record:
        return {"success": False, "message": "No pending registration found"}

    await db_delete_record_by_id(pending_record["id"])
    logger.info(f"Cancelled pending registration for {nip05_full}")
    return {"success": True, "message": "Registration cancelled"}


@router.post("/api/check-payment")
@limiter.limit("30/minute")
async def check_payment(request: Request, data: CheckPaymentRequest):
    if not LNURL or not LNKEY:
        raise HTTPException(status_code=500, detail="Lightning payment not configured")

    username = data.username.strip()
    pubkey_hex = convert_npub_to_hex(data.pubkey)
    payment_hash = data.payment_hash
    domain = data.domain

    registered_nip05 = await db_get_nip05_by_payment_hash(payment_hash)
    expected_nip05 = f"{username}@{domain}"
    if registered_nip05 != expected_nip05:
        logger.warning(
            f"Payment hijack attempt: hash {payment_hash[:16]}... "
            f"belongs to {registered_nip05!r}, claimed by {expected_nip05!r}"
        )
        raise HTTPException(status_code=400, detail="Payment hash does not match this registration")

    try:
        response = await payments_svc.http_client.get(
            f"{LNURL}/api/v1/payments/{payment_hash}",
            headers={"X-Api-Key": LNKEY},
        )
        if response.status_code != 200:
            return {"paid": False}

        payment_data = response.json()

        if payment_data.get("paid"):
            memo = payment_data.get("memo") or payment_data.get("description") or ""
            if memo:
                expected_memo = f"NIP-05: {username}@{domain}"
                if not memo.startswith("NIP-05:"):
                    logger.warning(f"Payment hash {payment_hash[:16]}... has unexpected memo: {memo}")
                    return {"paid": False}
                if memo != expected_memo:
                    logger.warning(f"Payment memo mismatch: expected '{expected_memo}', got '{memo}'")
                    return {"paid": False}
            else:
                logger.info(f"Payment hash {payment_hash[:16]}... has no memo, accepting")

            success = await check_and_add_nip05_entry_atomic(username, pubkey_hex, payment_hash, domain)
            if success:
                return {"paid": True}
            logger.warning(f"Payment verified but username {username} is already taken")
            return {"paid": False, "error": "Username already registered"}

        return {"paid": False}
    except httpx.RequestError as e:
        logger.error(f"LNbits connection error in check_payment: {e}")
        return {"paid": False}


@router.post("/api/register")
@limiter.limit("5/minute")
async def register_nip05(data: NIP05Request, request: Request):
    if not ADMIN_API_KEY:
        raise HTTPException(status_code=501, detail="Direct registration is disabled")

    provided_key = request.headers.get("X-Admin-Key", "")
    if not provided_key or not secrets.compare_digest(provided_key, ADMIN_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid admin API key")

    username = data.username.strip()
    pubkey_hex = convert_npub_to_hex(data.pubkey)
    domain = data.domain

    if not await check_and_add_nip05_entry(username, pubkey_hex, domain):
        raise HTTPException(status_code=400, detail="This NIP-05 identifier is already in use")

    await db_insert_record(
        nip05=f"{username}@{domain}",
        npub=data.pubkey,
        pubkey_hex=pubkey_hex,
        payment_completed=True,
        admin_only=True,
        in_nostr_json=True,
    )

    return {"success": True, "nip05": f"{username}@{domain}"}
