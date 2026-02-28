import logging
import aiosqlite
import time
from pathlib import Path

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent


async def get_schema_version(db: aiosqlite.Connection) -> int:
    try:
        cursor = await db.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        return row[0] if row else 0
    except aiosqlite.OperationalError:
        return 0


async def table_exists(db: aiosqlite.Connection, table_name: str) -> bool:
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return (await cursor.fetchone()) is not None


async def run_migrations(db: aiosqlite.Connection) -> None:
    current_version = await get_schema_version(db)
    
    migration_files = sorted(MIGRATIONS_DIR.glob("[0-9]*.py"))
    
    for migration_file in migration_files:
        if migration_file.stem.startswith("_"):
            continue
            
        try:
            module_name = migration_file.stem
            version = int(module_name.split("_")[0])
            
            if version > current_version:
                logger.info(f"Running migration {module_name} (version {version})")
                
                spec = __import__(
                    f"db.migrations.{module_name}",
                    fromlist=["upgrade"]
                )
                
                await spec.upgrade(db)
                
                await db.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                    (version, int(time.time()))
                )
                await db.commit()
                
                logger.info(f"Migration {module_name} completed successfully")
        except Exception as e:
            logger.error(f"Migration {module_name} failed: {e}")
            raise


async def init_schema_version(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at INTEGER NOT NULL
        )
    """)
    await db.commit()
