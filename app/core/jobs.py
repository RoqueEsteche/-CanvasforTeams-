"""Job/Task tracking system for recording all operations."""
import logging
from datetime import datetime
from typing import Optional
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

JOBS_DB = Path(__file__).parent.parent.parent / "data" / "jobs.db"


def init_jobs_db():
    """Initialize jobs database."""
    JOBS_DB.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(JOBS_DB)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            started_at DATETIME,
            completed_at DATETIME,
            job_type TEXT NOT NULL,
            operation TEXT NOT NULL,
            username TEXT,
            status TEXT DEFAULT 'pending',
            result_count INTEGER,
            error_count INTEGER,
            error_message TEXT,
            details TEXT,
            data_json TEXT
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_created_at ON jobs(created_at DESC)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_username ON jobs(username)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_job_type ON jobs(job_type)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_status ON jobs(status)
    """)

    conn.commit()
    conn.close()

    logger.info(f"Jobs database initialized: {JOBS_DB}")


async def create_job(
    job_type: str,
    operation: str,
    username: str,
    details: str = None,
    data_json: str = None
) -> int:
    """Create a new job record.

    Returns the job ID.
    """
    try:
        conn = sqlite3.connect(JOBS_DB)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO jobs (job_type, operation, username, details, data_json, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
        """, (job_type, operation, username, details, data_json))

        job_id = cursor.lastrowid
        conn.commit()
        conn.close()

        logger.info(f"Job created: ID={job_id}, type={job_type}, operation={operation}")
        return job_id

    except Exception as e:
        logger.error(f"Error creating job: {e}")
        return None


async def start_job(job_id: int):
    """Mark a job as started."""
    try:
        conn = sqlite3.connect(JOBS_DB)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE jobs
            SET status = 'processing', started_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (job_id,))

        conn.commit()
        conn.close()

        logger.debug(f"Job {job_id} started")

    except Exception as e:
        logger.error(f"Error starting job: {e}")


async def complete_job(
    job_id: int,
    result_count: int = 0,
    error_count: int = 0,
    error_message: str = None
):
    """Mark a job as completed."""
    try:
        conn = sqlite3.connect(JOBS_DB)
        cursor = conn.cursor()

        status = "completed" if error_count == 0 else "completed_with_errors"

        cursor.execute("""
            UPDATE jobs
            SET status = ?,
                completed_at = CURRENT_TIMESTAMP,
                result_count = ?,
                error_count = ?,
                error_message = ?
            WHERE id = ?
        """, (status, result_count, error_count, error_message, job_id))

        conn.commit()
        conn.close()

        logger.info(f"Job {job_id} completed: {result_count} success, {error_count} errors")

    except Exception as e:
        logger.error(f"Error completing job: {e}")


async def fail_job(job_id: int, error_message: str):
    """Mark a job as failed."""
    try:
        conn = sqlite3.connect(JOBS_DB)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE jobs
            SET status = 'failed',
                completed_at = CURRENT_TIMESTAMP,
                error_message = ?
            WHERE id = ?
        """, (error_message, job_id))

        conn.commit()
        conn.close()

        logger.warning(f"Job {job_id} failed: {error_message}")

    except Exception as e:
        logger.error(f"Error failing job: {e}")


async def get_jobs(
    limit: int = 100,
    offset: int = 0,
    job_type: str = None,
    username: str = None,
    status: str = None,
    date_from: str = None,
    date_to: str = None
) -> dict:
    """Get jobs with filters."""
    try:
        conn = sqlite3.connect(JOBS_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Build filter query
        where_clauses = []
        params = []

        if job_type:
            where_clauses.append("job_type = ?")
            params.append(job_type)

        if username:
            where_clauses.append("username = ?")
            params.append(username)

        if status:
            where_clauses.append("status = ?")
            params.append(status)

        if date_from:
            where_clauses.append("DATE(created_at) >= ?")
            params.append(date_from)

        if date_to:
            where_clauses.append("DATE(created_at) <= ?")
            params.append(date_to)

        where_clause = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        # Get total count
        cursor.execute(f"SELECT COUNT(*) FROM jobs{where_clause}", params)
        total = cursor.fetchone()[0]

        # Get jobs
        cursor.execute(
            f"""
            SELECT * FROM jobs
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset]
        )

        jobs = []
        for row in cursor.fetchall():
            jobs.append({
                "id": row["id"],
                "created_at": row["created_at"],
                "started_at": row["started_at"],
                "completed_at": row["completed_at"],
                "job_type": row["job_type"],
                "operation": row["operation"],
                "username": row["username"],
                "status": row["status"],
                "result_count": row["result_count"],
                "error_count": row["error_count"],
                "error_message": row["error_message"],
                "details": row["details"]
            })

        conn.close()

        return {
            "jobs": jobs,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        logger.error(f"Error retrieving jobs: {e}")
        return {"jobs": [], "total": 0, "limit": limit, "offset": offset}


async def get_jobs_stats(date_from: str = None, date_to: str = None) -> dict:
    """Get job statistics."""
    try:
        conn = sqlite3.connect(JOBS_DB)
        cursor = conn.cursor()

        where_clause = ""
        params = []

        if date_from or date_to:
            clauses = []
            if date_from:
                clauses.append("DATE(created_at) >= ?")
                params.append(date_from)
            if date_to:
                clauses.append("DATE(created_at) <= ?")
                params.append(date_to)
            where_clause = " WHERE " + " AND ".join(clauses)

        # Get stats
        cursor.execute(
            f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'completed_with_errors' THEN 1 ELSE 0 END) as with_errors,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = 'pending' OR status = 'processing' THEN 1 ELSE 0 END) as pending,
                SUM(COALESCE(result_count, 0)) as total_results,
                SUM(COALESCE(error_count, 0)) as total_errors
            FROM jobs
            {where_clause}
            """,
            params
        )

        row = cursor.fetchone()

        # Get by job type
        cursor.execute(
            f"""
            SELECT job_type, COUNT(*) as count, SUM(COALESCE(result_count, 0)) as results
            FROM jobs
            {where_clause}
            GROUP BY job_type
            ORDER BY count DESC
            """,
            params
        )

        by_type = {}
        for row_type in cursor.fetchall():
            by_type[row_type[0]] = {"count": row_type[1], "results": row_type[2]}

        # Get by user
        cursor.execute(
            f"""
            SELECT username, COUNT(*) as count, SUM(COALESCE(result_count, 0)) as results
            FROM jobs
            {where_clause}
            GROUP BY username
            ORDER BY count DESC
            """,
            params
        )

        by_user = {}
        for row_user in cursor.fetchall():
            by_user[row_user[0]] = {"count": row_user[1], "results": row_user[2]}

        conn.close()

        return {
            "total_jobs": row[0],
            "completed": row[1],
            "with_errors": row[2],
            "failed": row[3],
            "pending": row[4],
            "total_results": row[5],
            "total_errors": row[6],
            "by_type": by_type,
            "by_user": by_user
        }

    except Exception as e:
        logger.error(f"Error getting job stats: {e}")
        return {}
