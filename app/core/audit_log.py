"""Audit logging system to track all web service activities."""
import logging
import json
from datetime import datetime
from pathlib import Path
import sqlite3

logger = logging.getLogger(__name__)

AUDIT_DB = Path(__file__).parent.parent.parent / "data" / "audit.db"


def init_audit_db():
    """Initialize audit database."""
    AUDIT_DB.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(AUDIT_DB)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            username TEXT,
            endpoint TEXT,
            method TEXT,
            status_code INTEGER,
            ip_address TEXT,
            user_agent TEXT,
            details TEXT
        )
    """)

    conn.commit()
    conn.close()

    logger.info(f"Audit database initialized: {AUDIT_DB}")


async def log_activity(
    username: str,
    endpoint: str,
    method: str,
    status_code: int,
    ip_address: str,
    user_agent: str,
    details: str = None
):
    """Log an activity to the audit database."""
    try:
        conn = sqlite3.connect(AUDIT_DB)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO audit_logs (username, endpoint, method, status_code, ip_address, user_agent, details)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (username, endpoint, method, status_code, ip_address, user_agent, details))

        conn.commit()
        conn.close()

        logger.debug(f"Audit log: {username} {method} {endpoint} -> {status_code}")

    except Exception as e:
        logger.error(f"Error logging activity: {e}")


async def get_audit_logs(limit: int = 100, offset: int = 0):
    """Get audit logs from database."""
    try:
        conn = sqlite3.connect(AUDIT_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get total count
        cursor.execute("SELECT COUNT(*) FROM audit_logs")
        total = cursor.fetchone()[0]

        # Get logs
        cursor.execute("""
            SELECT * FROM audit_logs
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))

        logs = []
        for row in cursor.fetchall():
            logs.append({
                "id": row["id"],
                "timestamp": row["timestamp"],
                "username": row["username"],
                "endpoint": row["endpoint"],
                "method": row["method"],
                "status_code": row["status_code"],
                "ip_address": row["ip_address"],
                "user_agent": row["user_agent"],
                "details": row["details"]
            })

        conn.close()

        return {
            "logs": logs,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        logger.error(f"Error retrieving audit logs: {e}")
        return {"logs": [], "total": 0, "limit": limit, "offset": offset}


async def clear_old_logs(days: int = 90):
    """Clear audit logs older than N days."""
    try:
        conn = sqlite3.connect(AUDIT_DB)
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM audit_logs
            WHERE timestamp < datetime('now', ? || ' days')
        """, (f"-{days}",))

        deleted = cursor.rowcount
        conn.commit()
        conn.close()

        logger.info(f"Cleared {deleted} old audit logs (older than {days} days)")
        return deleted

    except Exception as e:
        logger.error(f"Error clearing old logs: {e}")
        return 0
