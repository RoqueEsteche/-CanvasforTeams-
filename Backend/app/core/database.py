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


async def upsert_courses(courses: list) -> int:
    """Upsert courses into database. Returns count of inserted/updated."""
    try:
        def _upsert():
            conn = sqlite3.connect(str(DB_FILE))
            cursor = conn.cursor()
            count = 0

            for course in courses:
                cursor.execute("""
                    INSERT OR REPLACE INTO canvas_courses (id, name, course_code, updated_at)
                    VALUES (?, ?, ?, ?)
                """, (
                    course.get('id'),
                    course.get('name', ''),
                    course.get('course_code', ''),
                    datetime.utcnow()
                ))
                count += 1

            conn.commit()
            conn.close()
            return count

        return await asyncio.to_thread(_upsert)
    except Exception as e:
        logger.error(f"Error upserting courses: {e}")
        return 0


async def upsert_canvas_users(users: list) -> int:
    """Upsert Canvas users into database. Returns count of inserted/updated."""
    try:
        def _upsert():
            conn = sqlite3.connect(str(DB_FILE))
            cursor = conn.cursor()
            count = 0

            for user in users:
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO canvas_users (id, name, email, login_id, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        user.get('id'),
                        user.get('name', ''),
                        user.get('email', ''),
                        user.get('login_id', ''),
                        datetime.utcnow()
                    ))
                    count += 1
                except Exception as e:
                    logger.warning(f"Skipping user {user.get('id')}: {e}")
                    continue

            conn.commit()
            conn.close()
            return count

        return await asyncio.to_thread(_upsert)
    except Exception as e:
        logger.error(f"Error upserting Canvas users: {e}")
        return 0


async def get_canvas_users() -> list:
    """Return all Canvas users from local DB."""
    try:
        def _get():
            conn = sqlite3.connect(str(DB_FILE))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, email, login_id FROM canvas_users ORDER BY name")
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return rows
        return await asyncio.to_thread(_get)
    except Exception as e:
        logger.error(f"Error getting Canvas users: {e}")
        return []


async def search_canvas_users(term: str, limit: int = 1000) -> list:
    """Search Canvas users in local DB by name, email or login_id."""
    try:
        def _search():
            conn = sqlite3.connect(str(DB_FILE))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            pattern = f"%{term}%"
            cursor.execute("""
                SELECT id, name, email, login_id FROM canvas_users
                WHERE name LIKE ? OR email LIKE ? OR login_id LIKE ?
                ORDER BY name LIMIT ?
            """, (pattern, pattern, pattern, limit))
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return rows
        return await asyncio.to_thread(_search)
    except Exception as e:
        logger.error(f"Error searching Canvas users: {e}")
        return []


async def delete_canvas_user(user_id: str) -> bool:
    """Delete a Canvas user from local DB."""
    try:
        def _del():
            conn = sqlite3.connect(str(DB_FILE))
            conn.execute("DELETE FROM canvas_users WHERE id = ?", (user_id,))
            conn.commit()
            conn.close()
        await asyncio.to_thread(_del)
        return True
    except Exception as e:
        logger.error(f"Error deleting Canvas user {user_id}: {e}")
        return False


async def get_courses() -> list:
    """Return all courses from local DB."""
    try:
        def _get():
            conn = sqlite3.connect(str(DB_FILE))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, course_code FROM canvas_courses ORDER BY name")
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return rows
        return await asyncio.to_thread(_get)
    except Exception as e:
        logger.error(f"Error getting courses: {e}")
        return []


async def delete_course(course_id: str) -> bool:
    """Delete a course from local DB."""
    try:
        def _del():
            conn = sqlite3.connect(str(DB_FILE))
            conn.execute("DELETE FROM canvas_courses WHERE id = ?", (course_id,))
            conn.commit()
            conn.close()
        await asyncio.to_thread(_del)
        return True
    except Exception as e:
        logger.error(f"Error deleting course {course_id}: {e}")
        return False


async def upsert_azure_users(users: list) -> int:
    """Upsert Azure AD users into local DB."""
    try:
        def _upsert():
            conn = sqlite3.connect(str(DB_FILE))
            cursor = conn.cursor()
            count = 0
            for user in users:
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO azure_users
                            (id, display_name, mail, user_principal_name, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        user.get('id'),
                        user.get('displayName', ''),
                        user.get('mail', ''),
                        user.get('userPrincipalName', ''),
                        datetime.utcnow()
                    ))
                    count += 1
                except Exception as ue:
                    logger.warning(f"Skipping Azure user {user.get('id')}: {ue}")
            conn.commit()
            conn.close()
            return count
        return await asyncio.to_thread(_upsert)
    except Exception as e:
        logger.error(f"Error upserting Azure users: {e}")
        return 0


async def get_azure_users(search: str | None = None) -> list:
    """Return Azure AD users from local DB, optionally filtered by search term."""
    try:
        def _get():
            conn = sqlite3.connect(str(DB_FILE))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if search:
                q = f"%{search.lower()}%"
                cursor.execute("""
                    SELECT id, display_name, mail, user_principal_name
                    FROM azure_users
                    WHERE lower(display_name) LIKE ?
                       OR lower(user_principal_name) LIKE ?
                       OR lower(coalesce(mail,'')) LIKE ?
                    ORDER BY display_name
                """, (q, q, q))
            else:
                cursor.execute("""
                    SELECT id, display_name, mail, user_principal_name
                    FROM azure_users ORDER BY display_name
                """)
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return rows
        return await asyncio.to_thread(_get)
    except Exception as e:
        logger.error(f"Error getting Azure users: {e}")
        return []


async def delete_azure_user(user_id: str) -> bool:
    """Delete an Azure AD user from local DB."""
    try:
        def _del():
            conn = sqlite3.connect(str(DB_FILE))
            conn.execute("DELETE FROM azure_users WHERE id = ?", (user_id,))
            conn.commit()
            conn.close()
        await asyncio.to_thread(_del)
        return True
    except Exception as e:
        logger.error(f"Error deleting Azure user {user_id}: {e}")
        return False


async def upsert_enrollments(enrollments: list) -> int:
    """Upsert enrollments into local DB."""
    try:
        def _upsert():
            conn = sqlite3.connect(str(DB_FILE))
            cursor = conn.cursor()
            count = 0
            for e in enrollments:
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO canvas_enrollments
                            (id, course_id, user_id, role)
                        VALUES (?, ?, ?, ?)
                    """, (
                        e.get('id'),
                        e.get('course_id'),
                        e.get('user_id'),
                        e.get('type', e.get('role', '')),
                    ))
                    count += 1
                except Exception as ue:
                    logger.warning(f"Skipping enrollment {e.get('id')}: {ue}")
            conn.commit()
            conn.close()
            return count
        return await asyncio.to_thread(_upsert)
    except Exception as e:
        logger.error(f"Error upserting enrollments: {e}")
        return 0


async def delete_enrollment(enrollment_id: str) -> bool:
    """Delete an enrollment from local DB."""
    try:
        def _del():
            conn = sqlite3.connect(str(DB_FILE))
            conn.execute("DELETE FROM canvas_enrollments WHERE id = ?", (enrollment_id,))
            conn.commit()
            conn.close()
        await asyncio.to_thread(_del)
        return True
    except Exception as e:
        logger.error(f"Error deleting enrollment {enrollment_id}: {e}")
        return False
