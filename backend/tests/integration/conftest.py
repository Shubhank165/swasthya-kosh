"""Integration fixtures.

These run against a real Postgres, because the two behaviours they prove —
`SELECT ... FOR UPDATE SKIP LOCKED` and true concurrent transactions — do not
exist on SQLite. Set `TEST_DATABASE_URL` to run them; without it they skip with
an explanatory message rather than passing vacuously.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings
from app.models import Base

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

requires_postgres = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason=(
        "set TEST_DATABASE_URL to a Postgres URL to run the concurrency suite; "
        "SQLite has no FOR UPDATE SKIP LOCKED, so these cannot be proven there"
    ),
)


@pytest_asyncio.fixture
async def pg_engine() -> AsyncIterator[AsyncEngine]:
    assert TEST_DATABASE_URL
    engine = create_async_engine(TEST_DATABASE_URL, future=True, pool_size=20, max_overflow=10)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_sessions(pg_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(pg_engine, expire_on_commit=False, class_=AsyncSession)


@pytest.fixture
def pg_settings() -> Settings:
    assert TEST_DATABASE_URL
    return Settings(environment="test", database_url=TEST_DATABASE_URL)
