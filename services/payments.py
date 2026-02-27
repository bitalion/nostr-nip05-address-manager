import logging
from urllib.parse import urlparse
import httpx
from config import LNURL, LNKEY

logger = logging.getLogger(__name__)

http_client: httpx.AsyncClient | None = None


def _validate_lnurl(url: str) -> None:
    if not url:
        return
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"LNBITS_URL must use http or https scheme, got: {parsed.scheme!r}")
    if not parsed.netloc:
        raise ValueError("LNBITS_URL must include a valid host")


async def get_payment_status_from_lnbits(payment_hash: str) -> dict | None:
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


async def get_invoice_from_lnbits(payment_hash: str) -> str | None:
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
