import logging
import time
import aiosqlite
from config import DB_PATH

logger = logging.getLogger(__name__)

_db_pool: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _db_pool
    if _db_pool is None:
        _db_pool = await aiosqlite.connect(DB_PATH)
        await _db_pool.execute("PRAGMA journal_mode=WAL")
        await _db_pool.execute("PRAGMA foreign_keys=ON")
    return _db_pool


async def init_db() -> None:
    from core.security import hash_password

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS records (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                nip05                TEXT    NOT NULL UNIQUE,
                npub                 TEXT    NOT NULL,
                pubkey_hex           TEXT    NOT NULL,
                payment_hash         TEXT,
                payment_completed    INTEGER NOT NULL DEFAULT 0,
                admin_only           INTEGER NOT NULL DEFAULT 0,
                registration_date    INTEGER NOT NULL,
                updated_at           INTEGER NOT NULL,
                in_nostr_json        INTEGER NOT NULL DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                username        TEXT    NOT NULL UNIQUE,
                password_hash   TEXT    NOT NULL,
                email           TEXT,
                role            TEXT    NOT NULL DEFAULT 'admin',
                created_at      INTEGER NOT NULL,
                last_login      INTEGER,
                is_active       INTEGER NOT NULL DEFAULT 1
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_nip05 ON records(nip05)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_npub ON records(pubkey_hex)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")

        try:
            await db.execute("ALTER TABLE users ADD COLUMN email TEXT")
        except aiosqlite.OperationalError as e:
            if "duplicate column name" not in str(e):
                raise

        await db.execute("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                token           TEXT    NOT NULL UNIQUE,
                expires_at      INTEGER NOT NULL,
                used            INTEGER NOT NULL DEFAULT 0,
                created_at      INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                token      TEXT    NOT NULL UNIQUE,
                user_id    INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token)")

        hashed = hash_password("manage")
        await db.execute(
            """INSERT OR IGNORE INTO users (username, password_hash, role, created_at)
               VALUES (?, ?, 'admin', ?)""",
            ("admin", hashed, int(time.time()))
        )

        await db.commit()
    logger.info(f"Database initialized at {DB_PATH}")
