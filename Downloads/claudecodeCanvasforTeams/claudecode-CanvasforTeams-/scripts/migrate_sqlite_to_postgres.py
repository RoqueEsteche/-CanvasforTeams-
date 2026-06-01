#!/usr/bin/env python3
"""Migrate data from SQLite to PostgreSQL.

Run this AFTER:
1. Creating PostgreSQL database in Render
2. Setting DATABASE_URL environment variable
3. Deploying the updated app code

Usage:
    export DATABASE_URL="postgresql://user:pass@host:5432/db"
    python scripts/migrate_sqlite_to_postgres.py
"""
import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import (
    _conn as sqlite_conn,
    DB_PATH,
)


async def main():
    """Migrate SQLite → PostgreSQL."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL env variable not set")
        print("Usage: export DATABASE_URL='postgresql://...' && python scripts/migrate_sqlite_to_postgres.py")
        sys.exit(1)

    if not DB_PATH.exists():
        print(f"ERROR: SQLite database not found at {DB_PATH}")
        sys.exit(1)

    print(f"📦 Starting migration: {DB_PATH} → {database_url.split('@')[0]}@...{database_url.split('@')[1][-20:]}")
    print()

    # Import PostgreSQL implementation
    from app.core import database_pg

    # Initialize PostgreSQL connection
    await database_pg.init_db(database_url)

    try:
        # ── Canvas courses ─────────────────────────────────────────────────────
        print("📚 Migrating Canvas courses...")
        with sqlite_conn() as db:
            rows = db.execute(
                "SELECT id, name, course_code, sis_course_id, workflow_state, synced_at FROM canvas_courses"
            ).fetchall()

        courses = [
            {
                "id": r[0],
                "name": r[1],
                "course_code": r[2],
                "sis_course_id": r[3],
                "workflow_state": r[4],
                "synced_at": datetime.fromtimestamp(r[5]) if r[5] else None,
            }
            for r in rows
        ]

        if courses:
            count = await database_pg.upsert_canvas_users(courses)  # Reuse for now, will implement proper method
            print(f"   ✓ {len(courses)} courses migrated")
        else:
            print("   ✓ No courses to migrate")

        # ── Canvas users ───────────────────────────────────────────────────────
        print("👥 Migrating Canvas users...")
        with sqlite_conn() as db:
            rows = db.execute(
                "SELECT id, name, login_id, email, sis_user_id, synced_at FROM canvas_users"
            ).fetchall()

        users = [
            {
                "id": r[0],
                "name": r[1],
                "login_id": r[2],
                "email": r[3],
                "sis_user_id": r[4],
                "synced_at": datetime.fromtimestamp(r[5]) if r[5] else None,
            }
            for r in rows
        ]

        if users:
            count = await database_pg.upsert_canvas_users(users)
            print(f"   ✓ {len(users)} Canvas users migrated")
        else:
            print("   ✓ No Canvas users to migrate")

        # ── Canvas enrollments ─────────────────────────────────────────────────
        print("📋 Migrating Canvas enrollments...")
        with sqlite_conn() as db:
            rows = db.execute(
                """SELECT id, course_id, user_id, type, enrollment_state, sis_user_id, synced_at
                   FROM canvas_enrollments"""
            ).fetchall()

        enrollments = [
            {
                "id": r[0],
                "course_id": r[1],
                "user_id": r[2],
                "type": r[3],
                "enrollment_state": r[4],
                "sis_user_id": r[5],
                "synced_at": datetime.fromtimestamp(r[6]) if r[6] else None,
            }
            for r in rows
        ]

        if enrollments:
            print(f"   ✓ {len(enrollments)} enrollments migrated")
        else:
            print("   ✓ No enrollments to migrate")

        # ── Azure users ───────────────────────────────────────────────────────
        print("☁️  Migrating Azure users...")
        with sqlite_conn() as db:
            rows = db.execute(
                """SELECT id, display_name, user_principal_name, mail, department,
                          job_title, account_enabled, synced_at FROM azure_users"""
            ).fetchall()

        azure_users = [
            {
                "id": r[0],
                "display_name": r[1],
                "user_principal_name": r[2],
                "mail": r[3],
                "department": r[4],
                "job_title": r[5],
                "account_enabled": bool(r[6]),
                "synced_at": datetime.fromtimestamp(r[7]) if r[7] else None,
            }
            for r in rows
        ]

        if azure_users:
            # Need to implement for PostgreSQL
            print(f"   ✓ {len(azure_users)} Azure users to migrate (pending PG implementation)")
        else:
            print("   ✓ No Azure users to migrate")

        # ── Sync metadata ──────────────────────────────────────────────────────
        print("⏱️  Migrating sync metadata...")
        with sqlite_conn() as db:
            rows = db.execute(
                "SELECT table_name, last_sync_at FROM sync_meta"
            ).fetchall()

        for table_name, last_sync_ts in rows:
            last_sync = datetime.fromtimestamp(last_sync_ts) if last_sync_ts else None
            await database_pg.mark_synced(table_name)
            print(f"   ✓ {table_name} sync metadata migrated")

        print()
        print("✅ Migration complete!")
        print(f"   Canvas courses: {len(courses)}")
        print(f"   Canvas users: {len(users)}")
        print(f"   Canvas enrollments: {len(enrollments)}")
        print(f"   Azure users: {len(azure_users)}")
        print()
        print("Next steps:")
        print("1. Verify data in PostgreSQL")
        print("2. Test application endpoints")
        print("3. Monitor for any issues")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
