"""Test fixtures.

Tests run against a real Postgres (the same server as dev, a separate database)
so JSONB columns, UUID types and constraints behave exactly as in production.

Loop discipline: the session-scoped fixture only creates/drops the database and
disposes its engine immediately. Every engine that a test actually uses is
function-scoped, so no connection is ever shared across event loops.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.db.base import Base
from app.db.seed import seed_job_roles
from app.db.session import get_db
from app.main import create_app
from app.services.storage import LocalResumeStorage

TEST_DB_NAME = f"{settings.POSTGRES_DB}_test"
TEST_DB_URL = (
    f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
    f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{TEST_DB_NAME}"
)

SAMPLE_DIR = Path(__file__).resolve().parents[1] / "sample_data"

# Child-first so foreign keys never block the truncate.
_TABLES = "resumes, screening_batches, job_descriptions, candidates, job_roles"


async def _admin_connection() -> asyncpg.Connection:
    return await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        database="postgres",
    )


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_database() -> AsyncGenerator[None, None]:
    """Create the test database and schema once, drop it at the end."""
    conn = await _admin_connection()
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    finally:
        await conn.close()

    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()

    yield

    conn = await _admin_connection()
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)')
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def test_engine(test_database):
    """A fresh engine bound to the running test's event loop.

    Wipes and re-seeds the schema first, so every test starts from the same
    known state: six system job roles and nothing else.
    """
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)

    async with engine.begin() as connection:
        await connection.execute(
            text(f"TRUNCATE TABLE {_TABLES} RESTART IDENTITY CASCADE")
        )

    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with factory() as db:
        await seed_job_roles(db)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(bind=test_engine, expire_on_commit=False, autoflush=False)
    async with factory() as db:
        yield db


@pytest_asyncio.fixture
async def client(test_engine, tmp_path, monkeypatch) -> AsyncGenerator[AsyncClient, None]:
    """An HTTP client wired to the test DB and a throwaway storage root."""
    test_storage = LocalResumeStorage(root=tmp_path / "resumes")
    test_storage.ensure_ready()
    monkeypatch.setattr("app.services.storage.resume_storage", test_storage)
    monkeypatch.setattr("app.services.resume_service.resume_storage", test_storage)
    monkeypatch.setattr("app.api.v1.endpoints.resumes.resume_storage", test_storage)

    factory = async_sessionmaker(bind=test_engine, expire_on_commit=False, autoflush=False)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as db:
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    # Drive the ASGI app without its lifespan: startup would seed the *dev*
    # database, which these tests must never touch.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def ai_role_id(client: AsyncClient) -> str:
    response = await client.get("/api/v1/job-roles/ai-engineer")
    return response.json()["id"]


def sample_bytes(name: str) -> bytes:
    return (SAMPLE_DIR / name).read_bytes()


@pytest.fixture
def resume_txt() -> tuple[str, bytes, str]:
    return ("rahul.txt", b"RAHUL SHARMA\nAI Engineer\nPython, RAG, PyTorch\n", "text/plain")


@pytest.fixture
def resume_pdf() -> tuple[str, bytes, str]:
    """A byte string with a real PDF header — enough for upload validation."""
    body = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EOF\n"
    return ("candidate.pdf", body, "application/pdf")
