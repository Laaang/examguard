import os
import aiosqlite
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from backend.app.config import DB_PATH
from backend.app.default_lists import (
    AI_CHEAT_DOMAINS,
    DOH_BYPASS_DOMAINS,
    SEARCH_DOMAINS,
    SOCIAL_DOMAINS,
    DEFAULT_WHITELIST_PRESETS,
)

@asynccontextmanager
async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode = WAL")
    await db.execute("PRAGMA synchronous = NORMAL")
    try:
        yield db
    finally:
        await db.close()

async def reset_classroom_data():
    """Briše sve studente i logove za novi ispit."""
    async with get_db() as db:
        await db.execute("DELETE FROM students")
        await db.execute("DELETE FROM query_logs")
        await db.commit()

async def init_db():
    async with get_db() as db:
        # 1. Sessions table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'whitelist',
                phase TEXT NOT NULL DEFAULT 'idle',
                checkin_duration_seconds INTEGER DEFAULT 120,
                checkin_started_at TEXT,
                exam_started_at TEXT,
                duration_minutes INTEGER DEFAULT 90,
                started_at TEXT,
                ended_at TEXT,
                is_active INTEGER DEFAULT 0
            )
        """)

        # Migracije stupaca ako tablica već postoji
        for col, col_def in [
            ("phase", "TEXT DEFAULT 'idle'"),
            ("checkin_duration_seconds", "INTEGER DEFAULT 120"),
            ("checkin_started_at", "TEXT"),
            ("exam_started_at", "TEXT"),
        ]:
            try:
                await db.execute(f"ALTER TABLE sessions ADD COLUMN {col} {col_def}")
            except Exception:
                pass

        # 2. Students / Workstations table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_address TEXT UNIQUE NOT NULL,
                workstation_name TEXT NOT NULL,
                full_name TEXT,
                student_id TEXT,
                checked_in_at TEXT,
                is_checked_in INTEGER DEFAULT 0,
                total_queries INTEGER DEFAULT 0,
                violations_count INTEGER DEFAULT 0,
                last_seen TEXT
            )
        """)

        # 3. Rules table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                rule_type TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'custom',
                is_enabled INTEGER DEFAULT 1,
                UNIQUE(domain, rule_type)
            )
        """)

        # 4. Query Logs table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS query_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                timestamp TEXT NOT NULL,
                client_ip TEXT NOT NULL,
                workstation_name TEXT NOT NULL,
                student_name TEXT,
                student_id TEXT,
                domain TEXT NOT NULL,
                query_type TEXT DEFAULT 'A',
                status TEXT NOT NULL,
                category TEXT,
                reason TEXT
            )
        """)

        # Indices
        await db.execute("CREATE INDEX IF NOT EXISTS idx_logs_session ON query_logs(session_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON query_logs(timestamp)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_logs_client_ip ON query_logs(client_ip)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_students_ip ON students(ip_address)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_rules_domain ON rules(domain)")

        await db.commit()

        # Seed initial rules if empty
        cursor = await db.execute("SELECT COUNT(*) as count FROM rules")
        row = await cursor.fetchone()
        if row and row["count"] == 0:
            rules_to_seed = []
            
            # AI Domene (Blacklist)
            for d in AI_CHEAT_DOMAINS:
                rules_to_seed.append((d, "blacklist", "ai_cheat", 1))
                
            # DoH Domene (Blacklist - Canary & Bypass)
            for d in DOH_BYPASS_DOMAINS:
                rules_to_seed.append((d, "blacklist", "doh_bypass", 1))
                
            # Search Domene (Blacklist)
            for d in SEARCH_DOMAINS:
                rules_to_seed.append((d, "blacklist", "search", 1))
                
            # Social Domene (Blacklist)
            for d in SOCIAL_DOMAINS:
                rules_to_seed.append((d, "blacklist", "social", 1))
                
            # Default Whitelist Domene
            for d in DEFAULT_WHITELIST_PRESETS:
                rules_to_seed.append((d, "whitelist", "educational", 1))

            await db.executemany("""
                INSERT OR IGNORE INTO rules (domain, rule_type, category, is_enabled)
                VALUES (?, ?, ?, ?)
            """, rules_to_seed)
            await db.commit()

        # Check if an active session exists; if not, create an initial default one
        cursor = await db.execute("SELECT * FROM sessions ORDER BY id DESC LIMIT 1")
        active = await cursor.fetchone()
        if not active:
            now = datetime.now(timezone.utc).isoformat()
            await db.execute("""
                INSERT INTO sessions (title, mode, phase, checkin_duration_seconds, duration_minutes, started_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ("Ispit iz Računalnih Mreža", "whitelist", "idle", 120, 90, now, 0))
            await db.commit()
