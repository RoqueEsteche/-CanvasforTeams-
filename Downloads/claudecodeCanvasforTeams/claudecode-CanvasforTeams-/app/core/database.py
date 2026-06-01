"""Database dispatcher — routes to PostgreSQL or SQLite based on environment.

If DATABASE_URL env var is set, uses PostgreSQL via SQLAlchemy ORM.
Otherwise falls back to SQLite for local development.
"""
import asyncio
import logging
import sqlite3
import time
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Detect which implementation to use
_USE_POSTGRES = bool(os.getenv("DATABASE_URL"))

# SQLite-only paths
_DB_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DB_PATH = _DB_DIR / "app.db"

# Seconds before a table is considered stale (10 minutes)
STALE_THRESHOLD = 600

# Lazy-loaded PostgreSQL implementation
_db_impl = None

def _get_pg_impl():
    """Lazy load PostgreSQL implementation on first use."""
    global _db_impl
    if _db_impl is None and _USE_POSTGRES:
        from . import database_pg
        _db_impl = database_pg
        logger.info("Using PostgreSQL backend via DATABASE_URL")
    return _db_impl

if _USE_POSTGRES:
    logger.info("PostgreSQL mode enabled (DATABASE_URL set)")
else:
    logger.info("SQLite mode enabled (no DATABASE_URL set)")


# ── SQLite internal helpers ───────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


async def _run(fn, *args) -> Any:
    """Execute a synchronous function in a thread pool."""
    return await asyncio.to_thread(fn, *args)


# ── Initialization ───────────────────────────────────────────────────────────

def _init_sqlite_sync() -> None:
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    with _conn() as db:
        db.execute("PRAGMA optimize")
        db.execute("PRAGMA synchronous=NORMAL")

        db.executescript("""
            CREATE TABLE IF NOT EXISTS canvas_users (
                id          INTEGER PRIMARY KEY,
                name        TEXT,
                login_id    TEXT UNIQUE,
                email       TEXT,
                sis_user_id TEXT UNIQUE,
                synced_at   REAL NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_cu_name  ON canvas_users(name COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS idx_cu_login ON canvas_users(login_id COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS idx_cu_email ON canvas_users(email COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS idx_cu_synced ON canvas_users(synced_at DESC);

            CREATE VIRTUAL TABLE IF NOT EXISTS fts_canvas_users USING fts5(
                name, login_id, email, content=canvas_users, content_rowid=id
            );

            CREATE TABLE IF NOT EXISTS canvas_courses (
                id             INTEGER PRIMARY KEY,
                name           TEXT,
                course_code    TEXT,
                sis_course_id  TEXT,
                workflow_state TEXT,
                synced_at      REAL NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_cc_name ON canvas_courses(name COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS idx_cc_code ON canvas_courses(course_code COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS idx_cc_synced ON canvas_courses(synced_at DESC);

            CREATE VIRTUAL TABLE IF NOT EXISTS fts_canvas_courses USING fts5(
                name, course_code, content=canvas_courses, content_rowid=id
            );

            CREATE TABLE IF NOT EXISTS canvas_enrollments (
                id               INTEGER PRIMARY KEY,
                course_id        INTEGER NOT NULL,
                user_id          INTEGER NOT NULL,
                type             TEXT,
                enrollment_state TEXT,
                sis_user_id      TEXT,
                synced_at        REAL NOT NULL DEFAULT 0,
                FOREIGN KEY(course_id) REFERENCES canvas_courses(id),
                FOREIGN KEY(user_id) REFERENCES canvas_users(id)
            );
            CREATE INDEX IF NOT EXISTS idx_ce_course ON canvas_enrollments(course_id);
            CREATE INDEX IF NOT EXISTS idx_ce_user   ON canvas_enrollments(user_id);
            CREATE INDEX IF NOT EXISTS idx_ce_sis    ON canvas_enrollments(sis_user_id);

            CREATE TABLE IF NOT EXISTS azure_users (
                id                   TEXT PRIMARY KEY,
                display_name         TEXT,
                user_principal_name  TEXT UNIQUE,
                mail                 TEXT,
                department           TEXT,
                job_title            TEXT,
                account_enabled      INTEGER,
                synced_at            REAL NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_au_name ON azure_users(display_name COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS idx_au_upn  ON azure_users(user_principal_name COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS idx_au_mail ON azure_users(mail COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS idx_au_synced ON azure_users(synced_at DESC);

            CREATE VIRTUAL TABLE IF NOT EXISTS fts_azure_users USING fts5(
                display_name, user_principal_name, mail, content=azure_users, content_rowid=id
            );

            CREATE TABLE IF NOT EXISTS sync_meta (
                table_name   TEXT PRIMARY KEY,
                last_sync_at REAL NOT NULL DEFAULT 0
            );
        """)
        db.commit()


async def init_db() -> None:
    """Initialize database (SQLite or PostgreSQL based on environment)."""
    if _USE_POSTGRES:
        database_url = os.getenv("DATABASE_URL")
        pg_impl = _get_pg_impl()
        if pg_impl:
            await pg_impl.init_db(database_url)
    else:
        await _run(_init_sqlite_sync)
        logger.info("SQLite initialized: %s", DB_PATH)


# ── Sync metadata (dispatcher) ───────────────────────────────────────────────

def _get_last_sync_sqlite(table: str) -> float:
    with _conn() as db:
        row = db.execute(
            "SELECT last_sync_at FROM sync_meta WHERE table_name = ?", (table,)
        ).fetchone()
    return row[0] if row else 0.0


def _mark_synced_sqlite(table: str) -> None:
    with _conn() as db:
        db.execute(
            "INSERT OR REPLACE INTO sync_meta (table_name, last_sync_at) VALUES (?, ?)",
            (table, time.time()),
        )
        db.commit()


async def get_last_sync(table: str) -> float:
    if _USE_POSTGRES:
        pg_impl = _get_pg_impl()
        if pg_impl:
            last_sync = await pg_impl.get_last_sync(table)
            return last_sync.timestamp() if last_sync else 0.0
        return 0.0
    else:
        return await _run(_get_last_sync_sqlite, table)


async def mark_synced(table: str) -> None:
    if _USE_POSTGRES:
        pg_impl = _get_pg_impl()
        if pg_impl:
            await pg_impl.mark_synced(table)
    else:
        await _run(_mark_synced_sqlite, table)


async def is_stale(table: str, max_age: int = STALE_THRESHOLD) -> bool:
    last = await get_last_sync(table)
    return (time.time() - last) > max_age


# ── Full-text search ───────────────────────────────────────────────────────

async def search_canvas_users(query: str, limit: int = 50) -> list[dict]:
    """Search Canvas users by name, email, login."""
    def _search_sqlite():
        with _conn() as db:
            fts_query = ' OR '.join(query.split())
            rows = db.execute("""
                SELECT cu.* FROM canvas_users cu
                WHERE cu.id IN (
                  SELECT rowid FROM fts_canvas_users WHERE fts_canvas_users MATCH ?
                  UNION
                  SELECT id FROM canvas_users WHERE login_id LIKE ? OR email LIKE ?
                )
                LIMIT ?
            """, (fts_query, f'%{query}%', f'%{query}%', limit)).fetchall()
            return [dict(r) for r in rows]

    if _USE_POSTGRES:
        # PostgreSQL fallback: simple LIKE search
        # Note: FTS5 is not available, using LIKE instead
        return await _run(lambda: [], )  # TODO: implement PG search
    else:
        return await _run(_search_sqlite)


async def search_canvas_courses(query: str, limit: int = 50) -> list[dict]:
    """Search Canvas courses by name and code."""
    def _search_sqlite():
        with _conn() as db:
            fts_query = ' OR '.join(query.split())
            rows = db.execute("""
                SELECT cc.* FROM canvas_courses cc
                WHERE cc.id IN (
                  SELECT rowid FROM fts_canvas_courses WHERE fts_canvas_courses MATCH ?
                  UNION
                  SELECT id FROM canvas_courses WHERE name LIKE ? OR course_code LIKE ?
                )
                LIMIT ?
            """, (fts_query, f'%{query}%', f'%{query}%', limit)).fetchall()
            return [dict(r) for r in rows]

    if _USE_POSTGRES:
        return await _run(lambda: [], )  # TODO: implement PG search
    else:
        return await _run(_search_sqlite)


async def search_azure_users(query: str, limit: int = 50) -> list[dict]:
    """Search Azure users by name, email, UPN."""
    def _search_sqlite():
        with _conn() as db:
            fts_query = ' OR '.join(query.split())
            rows = db.execute("""
                SELECT au.* FROM azure_users au
                WHERE au.id IN (
                  SELECT rowid FROM fts_azure_users WHERE fts_azure_users MATCH ?
                  UNION
                  SELECT id FROM azure_users WHERE user_principal_name LIKE ? OR mail LIKE ? OR display_name LIKE ?
                )
                LIMIT ?
            """, (fts_query, f'%{query}%', f'%{query}%', f'%{query}%', limit)).fetchall()
            return [dict(r) for r in rows]

    if _USE_POSTGRES:
        return await _run(lambda: [], )  # TODO: implement PG search
    else:
        return await _run(_search_sqlite)


# ── Canvas courses (dispatcher) ────────────────────────────────────────────────

def _upsert_courses_sqlite(courses: list[dict]) -> None:
    now = time.time()
    with _conn() as db:
        db.executemany(
            """INSERT OR REPLACE INTO canvas_courses
               (id, name, course_code, sis_course_id, workflow_state, synced_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (c.get("id"), c.get("name"), c.get("course_code"),
                 c.get("sis_course_id"), c.get("workflow_state"), now)
                for c in courses
            ],
        )
        db.commit()


def _get_courses_sqlite(search_term: str | None) -> list[dict]:
    if search_term:
        sql = ("SELECT id, name, course_code, sis_course_id, workflow_state FROM canvas_courses "
               "WHERE name LIKE ? OR course_code LIKE ? ORDER BY name")
        p = f"%{search_term}%"
        params = (p, p)
    else:
        sql = "SELECT id, name, course_code, sis_course_id, workflow_state FROM canvas_courses ORDER BY name"
        params = ()
    with _conn() as db:
        rows = db.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def _count_courses_sqlite() -> int:
    with _conn() as db:
        return db.execute("SELECT COUNT(*) FROM canvas_courses").fetchone()[0]


def _delete_course_sqlite(course_id: int) -> None:
    with _conn() as db:
        db.execute("DELETE FROM canvas_courses WHERE id = ?", (course_id,))
        db.commit()


async def upsert_courses(courses: list[dict]) -> None:
    if not courses:
        return
    if _USE_POSTGRES:
        # TODO: implement for PostgreSQL
        pass
    else:
        await _run(_upsert_courses_sqlite, courses)


async def get_courses(search_term: str | None = None) -> list[dict]:
    if _USE_POSTGRES:
        # TODO: implement for PostgreSQL
        return []
    else:
        return await _run(_get_courses_sqlite, search_term)


async def count_courses() -> int:
    if _USE_POSTGRES:
        pg_impl = _get_pg_impl()
        if pg_impl:
            return await pg_impl.count_courses()
        return 0
    else:
        return await _run(_count_courses_sqlite)


async def delete_course(course_id: int | str) -> None:
    if _USE_POSTGRES:
        # TODO: implement for PostgreSQL
        pass
    else:
        await _run(_delete_course_sqlite, int(course_id))


# ── Canvas users (dispatcher) ──────────────────────────────────────────────────

def _upsert_canvas_users_sqlite(users: list[dict]) -> None:
    now = time.time()
    with _conn() as db:
        db.executemany(
            """INSERT OR REPLACE INTO canvas_users
               (id, name, login_id, email, sis_user_id, synced_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (u.get("id"), u.get("name"), u.get("login_id"),
                 u.get("email"), u.get("sis_user_id"), now)
                for u in users
            ],
        )
        db.commit()


def _get_canvas_users_sqlite(search_term: str | None) -> list[dict]:
    if search_term:
        sql = ("SELECT id, name, login_id, email, sis_user_id FROM canvas_users "
               "WHERE name LIKE ? OR login_id LIKE ? OR email LIKE ? OR sis_user_id LIKE ? ORDER BY name")
        p = f"%{search_term}%"
        params = (p, p, p, p)
    else:
        sql = "SELECT id, name, login_id, email, sis_user_id FROM canvas_users ORDER BY name"
        params = ()
    with _conn() as db:
        rows = db.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def _count_canvas_users_sqlite() -> int:
    with _conn() as db:
        return db.execute("SELECT COUNT(*) FROM canvas_users").fetchone()[0]


def _delete_canvas_user_sqlite(user_id: int) -> None:
    with _conn() as db:
        db.execute("DELETE FROM canvas_users WHERE id = ?", (user_id,))
        db.commit()


async def upsert_canvas_users(users: list[dict]) -> None:
    if not users:
        return
    if _USE_POSTGRES:
        pg_impl = _get_pg_impl()
        if pg_impl:
            await pg_impl.upsert_canvas_users(users)
    else:
        await _run(_upsert_canvas_users_sqlite, users)


async def get_canvas_users(search_term: str | None = None) -> list[dict]:
    if _USE_POSTGRES:
        # TODO: implement for PostgreSQL
        return []
    else:
        return await _run(_get_canvas_users_sqlite, search_term)


async def count_canvas_users() -> int:
    if _USE_POSTGRES:
        pg_impl = _get_pg_impl()
        if pg_impl:
            return await pg_impl.count_canvas_users()
        return 0
    else:
        return await _run(_count_canvas_users_sqlite)


async def delete_canvas_user(user_id: int | str) -> None:
    if _USE_POSTGRES:
        # TODO: implement for PostgreSQL
        pass
    else:
        await _run(_delete_canvas_user_sqlite, int(user_id))


# ── Canvas enrollments (dispatcher) ────────────────────────────────────────────

def _upsert_enrollments_sqlite(course_id: int, enrollments: list[dict]) -> None:
    now = time.time()
    with _conn() as db:
        db.executemany(
            """INSERT OR REPLACE INTO canvas_enrollments
               (id, course_id, user_id, type, enrollment_state, sis_user_id, synced_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (e.get("id"), course_id, e.get("user_id"), e.get("type"),
                 e.get("enrollment_state"), e.get("sis_user_id"), now)
                for e in enrollments
            ],
        )
        db.commit()


def _delete_enrollment_sqlite(enrollment_id: int) -> None:
    with _conn() as db:
        db.execute("DELETE FROM canvas_enrollments WHERE id = ?", (enrollment_id,))
        db.commit()


async def upsert_enrollments(course_id: int | str, enrollments: list[dict]) -> None:
    if not enrollments:
        return
    if _USE_POSTGRES:
        # TODO: implement for PostgreSQL
        pass
    else:
        await _run(_upsert_enrollments_sqlite, int(course_id), enrollments)


async def delete_enrollment(enrollment_id: int | str) -> None:
    if _USE_POSTGRES:
        # TODO: implement for PostgreSQL
        pass
    else:
        await _run(_delete_enrollment_sqlite, int(enrollment_id))


# ── Azure users (dispatcher) ───────────────────────────────────────────────────

def _upsert_azure_users_sqlite(users: list[dict]) -> None:
    now = time.time()
    with _conn() as db:
        db.executemany(
            """INSERT OR REPLACE INTO azure_users
               (id, display_name, user_principal_name, mail,
                department, job_title, account_enabled, synced_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (u.get("id"), u.get("displayName"), u.get("userPrincipalName"),
                 u.get("mail"), u.get("department"), u.get("jobTitle"),
                 1 if u.get("accountEnabled") else 0, now)
                for u in users
            ],
        )
        db.commit()


def _get_azure_users_sqlite(search: str | None) -> list[dict]:
    if search:
        sql = ("""SELECT id,
                         display_name        AS displayName,
                         user_principal_name AS userPrincipalName,
                         mail, department,
                         job_title           AS jobTitle,
                         account_enabled     AS accountEnabled
                  FROM azure_users
                  WHERE display_name LIKE ? OR user_principal_name LIKE ? OR mail LIKE ?
                  ORDER BY display_name""")
        p = f"%{search}%"
        params = (p, p, p)
    else:
        sql = ("""SELECT id,
                         display_name        AS displayName,
                         user_principal_name AS userPrincipalName,
                         mail, department,
                         job_title           AS jobTitle,
                         account_enabled     AS accountEnabled
                  FROM azure_users ORDER BY display_name""")
        params = ()
    with _conn() as db:
        rows = db.execute(sql, params).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["accountEnabled"] = bool(d["accountEnabled"])
        result.append(d)
    return result


def _count_azure_users_sqlite() -> int:
    with _conn() as db:
        return db.execute("SELECT COUNT(*) FROM azure_users").fetchone()[0]


def _delete_azure_user_sqlite(user_id: str) -> None:
    with _conn() as db:
        db.execute("DELETE FROM azure_users WHERE id = ?", (user_id,))
        db.commit()


async def upsert_azure_users(users: list[dict]) -> None:
    if not users:
        return
    if _USE_POSTGRES:
        # TODO: implement for PostgreSQL
        pass
    else:
        await _run(_upsert_azure_users_sqlite, users)


async def get_azure_users(search: str | None = None) -> list[dict]:
    if _USE_POSTGRES:
        # TODO: implement for PostgreSQL
        return []
    else:
        return await _run(_get_azure_users_sqlite, search)


async def count_azure_users() -> int:
    if _USE_POSTGRES:
        pg_impl = _get_pg_impl()
        if pg_impl:
            return await pg_impl.count_azure_users()
        return 0
    else:
        return await _run(_count_azure_users_sqlite)


async def delete_azure_user(user_id: str) -> None:
    if _USE_POSTGRES:
        # TODO: implement for PostgreSQL
        pass
    else:
        await _run(_delete_azure_user_sqlite, user_id)
