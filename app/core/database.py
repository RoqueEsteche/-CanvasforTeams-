"""Database module - handles SQLite and PostgreSQL operations."""
import sqlite3
import asyncio
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Database file location
DB_FILE = Path(__file__).parent.parent.parent / "app.db"


async def init_db():
    """Initialize database - create tables if needed."""
    try:
        def _init():
            conn = sqlite3.connect(str(DB_FILE))
            cursor = conn.cursor()

            # Create main tables
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS canvas_courses (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    course_code TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS canvas_users (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE,
                    login_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS canvas_enrollments (
                    id INTEGER PRIMARY KEY,
                    course_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    role TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (course_id) REFERENCES canvas_courses(id),
                    FOREIGN KEY (user_id) REFERENCES canvas_users(id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS azure_users (
                    id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    mail TEXT UNIQUE,
                    user_principal_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sync_metadata (
                    id INTEGER PRIMARY KEY,
                    sync_type TEXT NOT NULL,
                    last_sync TIMESTAMP,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(sync_type)
                )
            """)

            conn.commit()
            conn.close()
            logger.info(f"Database initialized at {DB_FILE}")

        await asyncio.to_thread(_init)
    except Exception as e:
        logger.error(f"Database initialization error: {e}", exc_info=True)
        raise


async def count_courses() -> int:
    """Count total courses."""
    try:
        def _count():
            conn = sqlite3.connect(str(DB_FILE))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM canvas_courses")
            count = cursor.fetchone()[0]
            conn.close()
            return count

        return await asyncio.to_thread(_count)
    except Exception as e:
        logger.error(f"Error counting courses: {e}")
        return 0


async def count_canvas_users() -> int:
    """Count total Canvas users."""
    try:
        def _count():
            conn = sqlite3.connect(str(DB_FILE))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM canvas_users")
            count = cursor.fetchone()[0]
            conn.close()
            return count

        return await asyncio.to_thread(_count)
    except Exception as e:
        logger.error(f"Error counting Canvas users: {e}")
        return 0


async def count_azure_users() -> int:
    """Count total Azure users."""
    try:
        def _count():
            conn = sqlite3.connect(str(DB_FILE))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM azure_users")
            count = cursor.fetchone()[0]
            conn.close()
            return count

        return await asyncio.to_thread(_count)
    except Exception as e:
        logger.error(f"Error counting Azure users: {e}")
        return 0


async def mark_synced(sync_type: str) -> bool:
    """Mark a sync as completed."""
    try:
        def _mark():
            conn = sqlite3.connect(str(DB_FILE))
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO sync_metadata (sync_type, last_sync, status)
                VALUES (?, ?, 'completed')
            """, (sync_type, datetime.utcnow()))
            conn.commit()
            conn.close()
            return True

        return await asyncio.to_thread(_mark)
    except Exception as e:
        logger.error(f"Error marking sync: {e}")
        return False


async def get_last_sync(sync_type: str) -> datetime | None:
    """Get the last sync time for a specific type."""
    try:
        def _get():
            conn = sqlite3.connect(str(DB_FILE))
            cursor = conn.cursor()
            cursor.execute("""
                SELECT last_sync FROM sync_metadata WHERE sync_type = ?
            """, (sync_type,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else None

        result = await asyncio.to_thread(_get)
        return datetime.fromisoformat(result) if result else None
    except Exception as e:
        logger.error(f"Error getting last sync: {e}")
        return None


async def is_stale(sync_type: str, ttl_seconds: int = 3600) -> bool:
    """Check if a sync is stale (older than TTL)."""
    try:
        last_sync = await get_last_sync(sync_type)
        if not last_sync:
            return True

        time_elapsed = (datetime.utcnow() - last_sync).total_seconds()
        return time_elapsed > ttl_seconds
    except Exception as e:
        logger.error(f"Error checking staleness: {e}")
        return True
