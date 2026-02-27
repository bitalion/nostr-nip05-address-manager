import logging
import time
import secrets
import aiosqlite
from db.connection import get_db

logger = logging.getLogger(__name__)


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
        "UPDATE users SET email = ? WHERE id = ?", (email, user_id)
    )
    await db.commit()
    return cursor.rowcount > 0


async def create_user(username: str, password: str, email: str | None, role: str) -> int:
    from core.security import hash_password
    db = await get_db()
    password_hash = hash_password(password)
    timestamp = int(time.time())
    try:
        cursor = await db.execute(
            "INSERT INTO users (username, password_hash, email, role, created_at) VALUES (?, ?, ?, ?, ?)",
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
    from core.security import hash_password
    db = await get_db()
    password_hash = hash_password(new_password)
    cursor = await db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id)
    )
    await db.commit()
    return cursor.rowcount > 0


async def update_user_password(user_id: int, new_password: str) -> bool:
    from core.security import hash_password
    db = await get_db()
    password_hash = hash_password(new_password)
    cursor = await db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id)
    )
    await db.commit()
    return cursor.rowcount > 0


async def authenticate_user(username: str, password: str) -> dict | None:
    from core.security import verify_password
    db = await get_db()
    db.row_factory = aiosqlite.Row
    cursor = await db.execute(
        "SELECT * FROM users WHERE username = ? AND is_active = 1", (username.lower(),)
    )
    row = await cursor.fetchone()
    if not row:
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    await db.execute(
        "UPDATE users SET last_login = ? WHERE id = ?", (int(time.time()), row["id"])
    )
    await db.commit()
    return {"id": row["id"], "username": row["username"], "role": row["role"]}


async def create_password_reset_token(username: str) -> tuple[str, int] | None:
    db = await get_db()
    db.row_factory = aiosqlite.Row
    cursor = await db.execute(
        "SELECT id FROM users WHERE LOWER(username) = ? AND is_active = 1",
        (username.lower(),)
    )
    row = await cursor.fetchone()
    if not row:
        return None

    token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + 3600

    await db.execute(
        "INSERT INTO password_reset_tokens (user_id, token, expires_at, created_at) VALUES (?, ?, ?, ?)",
        (row["id"], token, expires_at, int(time.time()))
    )
    await db.commit()
    return token, expires_at


async def verify_password_reset_token(token: str) -> int | None:
    db = await get_db()
    db.row_factory = aiosqlite.Row
    cursor = await db.execute(
        "SELECT user_id FROM password_reset_tokens WHERE token = ? AND used = 0 AND expires_at > ?",
        (token, int(time.time()))
    )
    row = await cursor.fetchone()
    return row["user_id"] if row else None


async def use_password_reset_token(token: str) -> bool:
    db = await get_db()
    cursor = await db.execute(
        "UPDATE password_reset_tokens SET used = 1 WHERE token = ?", (token,)
    )
    await db.commit()
    return cursor.rowcount > 0
