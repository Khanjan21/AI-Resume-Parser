"""Test fixtures.

Tests run against a real Postgres (the same server as dev, a separate database)
so JSONB columns, UUID types and constraints behave exactly as in production.

Loop discipline: the session-scoped fixture only creates/drops the database and
disposes its engine immediately. Every engine that a test actually uses is
function-scoped, so no connection is ever shared across event loops.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

# Windows' default ProactorEventLoop has a known bad interaction with asyncpg
# during teardown (IOCP handles torn down out of order -> "Event loop is
# closed" / "'NoneType' object has no attribute 'send'" mid-rollback). The
# Selector loop has none of Proactor's subprocess/pipe support, which these
# tests never need, and doesn't hit this.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

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
        # Base.metadata.create_all bypasses Alembic (and its migration that
        # enables this) entirely — without it, creating any `vector(...)`
        # column fails with "type vector does not exist".
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()

    yield

    conn = await _admin_connection()
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)')
    finally:
        await conn.close()


@pytest_asyncio.fixture(loop_scope="function")
async def test_engine(test_database, fake_embeddings):
    """A fresh engine bound to the running test's event loop.

    Wipes and re-seeds the schema first, so every test starts from the same
    known state: six system job roles and nothing else. Seeding now computes
    an embedding per role — `fake_embeddings` must be set up *before* that
    runs, which is exactly why it's a dependency here rather than only on
    `client`/`parsing_env`: those patch scoring/parsing's usage, but seeding
    happens inside this fixture's own body, before either of those get a
    chance to apply anything.

    loop_scope="function" matters here: the ini default is "session", but any
    fixture that hands out a *live* connection/session the test body will use
    (this one, `session`, `parsing_env`) must run on the same loop as the test
    body itself, or asyncpg's low-level transport — bound to whichever loop
    was running when the connection was actually opened — mismatches the loop
    driving the fixture's own teardown, surfacing as "Future attached to a
    different loop" or a flat-out hang. `client` is exempt: its connections
    are opened and fully discarded inside `override_get_db` during the test
    body's own request cycle, never touched again by fixture teardown code.
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


@pytest_asyncio.fixture(loop_scope="function")
async def session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Committing on exit matters here: leaving an active (even read-only,
    e.g. from a trailing `session.get`/`refresh`) transaction for `__aexit__`
    to implicitly roll back races with event-loop teardown on Windows'
    ProactorEventLoop and surfaces as 'Event loop is closed' at teardown."""
    factory = async_sessionmaker(bind=test_engine, expire_on_commit=False, autoflush=False)
    async with factory() as db:
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise


class FakeLLMProvider:
    """Stands in for GroqProvider — no network call, no real API key needed.

    `response` and `error` are None by default, meaning "succeed with an
    empty-but-valid instance of whatever schema was requested." Tests that
    care about the extracted content set `.response` before triggering the
    parse; tests that care about failure handling set `.error`.
    """

    def __init__(self) -> None:
        self.response = None
        self.error: Exception | None = None
        self.calls: list[dict] = []

    async def extract(
        self, *, system_prompt, user_content, response_model, tool_name, tool_description
    ):
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_content": user_content,
                "tool_name": tool_name,
            }
        )
        if self.error is not None:
            raise self.error
        if self.response is not None:
            return self.response
        return response_model()


@pytest.fixture
def fake_llm(monkeypatch) -> FakeLLMProvider:
    """Replaces the real Groq provider everywhere parsing_service looks it up.

    Also forces PARSE_ON_UPLOAD/GROQ_API_KEY on so upload endpoints queue the
    background parse regardless of what the real .env happens to contain —
    tests must not depend on local environment state.
    """
    provider = FakeLLMProvider()
    monkeypatch.setattr("app.services.parsing_service.get_llm_provider", lambda: provider)
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(settings, "PARSE_ON_UPLOAD", True)
    return provider


class FakeEmbeddingProvider:
    """Stands in for BgeEmbeddingProvider — no model download, no ~7s load.

    Vectors are deterministic (seeded from a hash of the text) and unit-length,
    so identical text always embeds identically and cosine similarity math
    behaves correctly — but they carry none of the real model's semantic
    meaning. That's fine here: this fixture verifies the *wiring* (does a
    semantic_score get computed, does it feed into final_score, does an
    embedding get persisted and reused), not similarity quality — the real
    model's actual behaviour was calibrated separately against known text
    pairs (see the Day 4 section in the README) rather than re-verified here.
    """

    dimensions = 384

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        import hashlib
        import random

        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16)
        rng = random.Random(seed)
        raw = [rng.uniform(-1.0, 1.0) for _ in range(self.dimensions)]
        norm = sum(x * x for x in raw) ** 0.5
        return [x / norm for x in raw]


@pytest.fixture
def fake_embeddings(monkeypatch) -> FakeEmbeddingProvider:
    """Replaces the real embedding provider everywhere Day 4 code looks it up:
    role seeding, JD parsing, and resume scoring."""
    provider = FakeEmbeddingProvider()
    monkeypatch.setattr("app.db.seed.get_embedding_provider", lambda: provider)
    monkeypatch.setattr("app.services.scoring_service.get_embedding_provider", lambda: provider)
    monkeypatch.setattr("app.services.parsing_service.get_embedding_provider", lambda: provider)
    return provider


@pytest_asyncio.fixture(loop_scope="function")
async def parsing_env(test_engine, tmp_path, monkeypatch) -> LocalResumeStorage:
    """Isolates `parsing_service` (and the `scoring_service` it triggers after
    a successful parse) for tests that call it directly (no HTTP layer) —
    same idea as `client`'s patches, without spinning up the app."""
    factory = async_sessionmaker(bind=test_engine, expire_on_commit=False, autoflush=False)
    monkeypatch.setattr("app.services.parsing_service.AsyncSessionLocal", factory)
    # scoring_service imports its own AsyncSessionLocal reference (module-level,
    # independent of parsing_service's) — miss this and score_resume() silently
    # connects to the real dev database instead of the test one.
    monkeypatch.setattr("app.services.scoring_service.AsyncSessionLocal", factory)

    storage = LocalResumeStorage(root=tmp_path / "resumes")
    storage.ensure_ready()
    monkeypatch.setattr("app.services.parsing_service.resume_storage", storage)
    return storage


@pytest_asyncio.fixture(loop_scope="function")
async def client(
    test_engine, tmp_path, monkeypatch, fake_llm: FakeLLMProvider
) -> AsyncGenerator[AsyncClient, None]:
    """An HTTP client wired to the test DB and a throwaway storage root.

    Any background parse task a request queues must also land in the test DB
    and test storage, never the real ones — `parsing_service` (and the
    `scoring_service` it triggers after a successful parse) get their own
    copies of `AsyncSessionLocal` and `resume_storage` patched here.
    """
    test_storage = LocalResumeStorage(root=tmp_path / "resumes")
    test_storage.ensure_ready()
    monkeypatch.setattr("app.services.storage.resume_storage", test_storage)
    monkeypatch.setattr("app.services.resume_service.resume_storage", test_storage)
    monkeypatch.setattr("app.api.v1.endpoints.resumes.resume_storage", test_storage)
    monkeypatch.setattr("app.services.parsing_service.resume_storage", test_storage)

    factory = async_sessionmaker(bind=test_engine, expire_on_commit=False, autoflush=False)
    monkeypatch.setattr("app.services.parsing_service.AsyncSessionLocal", factory)
    monkeypatch.setattr("app.services.scoring_service.AsyncSessionLocal", factory)

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
    """A byte string with a real PDF header — enough for upload validation, but
    with no page tree, so text extraction is expected to fail on this one."""
    body = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EOF\n"
    return ("candidate.pdf", body, "application/pdf")


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def build_pdf_bytes(text: str) -> bytes:
    """A genuinely valid single-page PDF containing `text`, byte-correct xref
    included. Mirrors `scripts/make_sample_resumes.write_pdf` — kept as a
    standalone duplicate so tests don't depend on the demo script."""
    lines = [line for line in text.splitlines() if line.strip()][:55]
    content_ops = ["BT", "/F1 11 Tf", "12 TL"]
    y = 740
    for line in lines:
        content_ops.append(f"1 0 0 1 50 {y} Tm ({_escape_pdf_text(line)}) Tj")
        y -= 13
    content_ops.append("ET")
    content_bytes = "\n".join(content_ops).encode("latin-1", errors="replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 612 792] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content_bytes)).encode() + b" >>\nstream\n"
        + content_bytes + b"\nendstream",
    ]

    buf = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(buf))
        buf += f"{index} 0 obj\n".encode()
        buf += obj
        buf += b"\nendobj\n"

    xref_offset = len(buf)
    count = len(objects) + 1
    buf += f"xref\n0 {count}\n".encode()
    buf += b"0000000000 65535 f \n"
    for offset in offsets:
        buf += f"{offset:010d} 00000 n \n".encode()
    buf += (
        f"trailer\n<< /Size {count} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF"
    ).encode()
    return bytes(buf)


@pytest.fixture
def real_pdf_bytes() -> bytes:
    """A PDF that text_extraction can genuinely pull text out of."""
    return build_pdf_bytes(
        "JANE DOE\nData Scientist\njane.doe@example.com\nSkills: Python, SQL, Statistics"
    )
