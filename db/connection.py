import logging
import time
import aiosqlite
from config import DB_PATH
from db.migrations.manager import init_schema_version, run_migrations

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
    async with aiosqlite.connect(DB_PATH) as db:
        await init_schema_version(db)
        await run_migrations(db)
        
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        
    logger.info(f"Database initialized at {DB_PATH}")
