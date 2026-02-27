import hashlib
import hmac
import secrets
import logging
import time
from fastapi import Depends, HTTPException, Request

logger = logging.getLogger(__name__)

SESSION_TTL = 86400  # 24 hours


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


async def create_token(user: dict) -> str:
    import aiosqlite
    from db.connection import get_db
    token = secrets.token_hex(32)
    now = int(time.time())
    db = await get_db()
    db.row_factory = aiosqlite.Row
    await db.execute(
        "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
        (token, user["id"], now + SESSION_TTL, now)
    )
    await db.commit()
    return token


async def verify_token(token: str) -> dict | None:
    import aiosqlite
    from db.connection import get_db
    db = await get_db()
    db.row_factory = aiosqlite.Row
    now = int(time.time())
    cursor = await db.execute(
        """SELECT u.id, u.username, u.role
           FROM sessions s
           JOIN users u ON u.id = s.user_id
           WHERE s.token = ? AND s.expires_at > ? AND u.is_active = 1""",
        (token, now)
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return {"id": row["id"], "username": row["username"], "role": row["role"]}


async def invalidate_token(token: str) -> None:
    from db.connection import get_db
    db = await get_db()
    await db.execute("DELETE FROM sessions WHERE token = ?", (token,))
    await db.commit()


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await verify_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user


def require_role(required_role: str):
    async def role_checker(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("role") != required_role and current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return role_checker
