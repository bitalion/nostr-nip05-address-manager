import aiosqlite


async def upgrade(db: aiosqlite.Connection) -> None:
    from db.migrations.manager import table_exists
    
    if not await table_exists(db, "records"):
        await db.execute("""
            CREATE TABLE records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nip05 TEXT NOT NULL UNIQUE,
                npub TEXT NOT NULL,
                pubkey_hex TEXT NOT NULL,
                payment_hash TEXT,
                payment_completed INTEGER NOT NULL DEFAULT 0,
                admin_only INTEGER NOT NULL DEFAULT 0,
                registration_date INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                in_nostr_json INTEGER NOT NULL DEFAULT 0
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_nip05 ON records(nip05)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_pubkey_hex ON records(pubkey_hex)")
    
    if not await table_exists(db, "users"):
        await db.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                email TEXT,
                role TEXT NOT NULL DEFAULT 'admin',
                created_at INTEGER NOT NULL,
                last_login INTEGER,
                is_active INTEGER NOT NULL DEFAULT 1
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        
        import time
        from core.security import hash_password
        hashed = hash_password("manage")
        await db.execute(
            """INSERT OR IGNORE INTO users (username, password_hash, role, created_at)
               VALUES (?, ?, 'admin', ?)""",
            ("admin", hashed, int(time.time()))
        )
    
    if not await table_exists(db, "password_reset_tokens"):
        await db.execute("""
            CREATE TABLE password_reset_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT NOT NULL UNIQUE,
                expires_at INTEGER NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
    
    if not await table_exists(db, "sessions"):
        await db.execute("""
            CREATE TABLE sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL UNIQUE,
                user_id INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token)")
