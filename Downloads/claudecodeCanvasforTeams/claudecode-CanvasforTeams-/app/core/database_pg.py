"""PostgreSQL database implementation using SQLAlchemy ORM."""
import asyncio
import logging
from typing import Any, Optional
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, create_engine, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

Base = declarative_base()
_engine = None
_async_session = None

# ── Database Models ──────────────────────────────────────────────────────────

class CanvasUser(Base):
    __tablename__ = "canvas_users"
    id = Column(Integer, primary_key=True)
    name = Column(String, index=True)
    login_id = Column(String, unique=True, index=True)
    email = Column(String, index=True)
    sis_user_id = Column(String)
    synced_at = Column(DateTime, index=True)

class CanvasCourse(Base):
    __tablename__ = "canvas_courses"
    id = Column(Integer, primary_key=True)
    name = Column(String, index=True)
    course_code = Column(String, index=True)
    sis_course_id = Column(String)
    workflow_state = Column(String)
    synced_at = Column(DateTime, index=True)

class CanvasEnrollment(Base):
    __tablename__ = "canvas_enrollments"
    id = Column(Integer, primary_key=True)
    course_id = Column(Integer, index=True)
    user_id = Column(Integer, index=True)
    type = Column(String)
    enrollment_state = Column(String)
    sis_user_id = Column(String, index=True)
    synced_at = Column(DateTime, index=True)

class AzureUser(Base):
    __tablename__ = "azure_users"
    id = Column(String, primary_key=True)
    display_name = Column(String, index=True)
    user_principal_name = Column(String, index=True)
    mail = Column(String, index=True)
    department = Column(String)
    job_title = Column(String)
    account_enabled = Column(Boolean)
    synced_at = Column(DateTime, index=True)

class SyncMeta(Base):
    __tablename__ = "sync_meta"
    table_name = Column(String, primary_key=True)
    last_sync_at = Column(DateTime)

# ── Initialization ───────────────────────────────────────────────────────────

async def init_db(database_url: str) -> None:
    """Initialize PostgreSQL database with tables."""
    global _engine, _async_session

    _engine = create_async_engine(
        database_url,
        echo=False,
        poolclass=NullPool,
        connect_args={"timeout": 30}
    )
    _async_session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("PostgreSQL database initialized")

# ── Helper functions ────────────────────────────────────────────────────────

async def _get_session() -> AsyncSession:
    """Get an async database session."""
    if _async_session is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _async_session()

async def _run(fn, *args) -> Any:
    """Execute a synchronous function in a thread pool."""
    return await asyncio.to_thread(fn, *args)

# ── Canvas Users ─────────────────────────────────────────────────────────────

async def upsert_canvas_users(users: list[dict]) -> int:
    """Upsert Canvas users."""
    if not users:
        return 0

    session = await _get_session()
    try:
        for user in users:
            stmt = select(CanvasUser).where(CanvasUser.id == user.get('id'))
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                for key, value in user.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
            else:
                session.add(CanvasUser(**user))

        await session.commit()
        return len(users)
    finally:
        await session.close()

async def count_courses() -> int:
    """Get total course count."""
    session = await _get_session()
    try:
        result = await session.execute(select(CanvasCourse))
        return len(result.scalars().all())
    finally:
        await session.close()

async def count_canvas_users() -> int:
    """Get total Canvas user count."""
    session = await _get_session()
    try:
        result = await session.execute(select(CanvasUser))
        return len(result.scalars().all())
    finally:
        await session.close()

async def count_azure_users() -> int:
    """Get total Azure user count."""
    session = await _get_session()
    try:
        result = await session.execute(select(AzureUser))
        return len(result.scalars().all())
    finally:
        await session.close()

# ── Sync metadata ────────────────────────────────────────────────────────────

async def mark_synced(table_name: str) -> None:
    """Mark a table as synced."""
    session = await _get_session()
    try:
        stmt = select(SyncMeta).where(SyncMeta.table_name == table_name)
        result = await session.execute(stmt)
        meta = result.scalar_one_or_none()

        if meta:
            meta.last_sync_at = datetime.utcnow()
        else:
            session.add(SyncMeta(table_name=table_name, last_sync_at=datetime.utcnow()))

        await session.commit()
    finally:
        await session.close()

async def get_last_sync(table_name: str) -> Optional[datetime]:
    """Get last sync time for a table."""
    session = await _get_session()
    try:
        stmt = select(SyncMeta).where(SyncMeta.table_name == table_name)
        result = await session.execute(stmt)
        meta = result.scalar_one_or_none()
        return meta.last_sync_at if meta else None
    finally:
        await session.close()

async def is_stale(table_name: str, threshold_seconds: int = 600) -> bool:
    """Check if a table is stale."""
    last_sync = await get_last_sync(table_name)
    if not last_sync:
        return True
    return (datetime.utcnow() - last_sync).total_seconds() > threshold_seconds
