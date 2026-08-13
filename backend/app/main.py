"""FastAPI application factory and lifespan wiring."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.endpoints import health
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.db.seed import run_seed
from app.db.session import engine
from app.services.embedding import get_embedding_provider
from app.services.storage import resume_storage

configure_logging()
logger = get_logger(__name__)

DESCRIPTION = """
AI-powered resume screening and intelligent candidate shortlisting.

**Candidate flow** — pick a role, upload a resume, get an ATS score, job-fit
score, matched/missing skills and improvement suggestions.

**Recruiter flow** — pick a role, bulk-upload resumes, get per-candidate scores,
ranking and shortlist categories, then interrogate the results with RAG.

Day 1 ships the foundation: job-role catalogue, database, upload pipeline.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s (%s)", settings.PROJECT_NAME, settings.VERSION, settings.ENVIRONMENT)

    resume_storage.ensure_ready()
    logger.info("Resume storage ready at %s", resume_storage.root)

    if settings.WARM_UP_EMBEDDING_MODEL:
        try:
            # Loading BGE-small takes several seconds (model weights from
            # disk, or a one-time download). Paying that cost here means the
            # first real resume score isn't the one that eats it — and
            # run_seed() below needs the model ready anyway for any role
            # missing an embedding.
            await asyncio.to_thread(get_embedding_provider)
            logger.info("Embedding model ready.")
        except Exception as exc:  # noqa: BLE001 - semantic scoring degrades, app still boots
            logger.warning(
                "Embedding model warm-up failed (%s). Semantic scoring will be "
                "unavailable until it loads successfully.",
                exc,
            )

    if settings.SEED_ON_STARTUP:
        try:
            await run_seed()
        except Exception as exc:  # noqa: BLE001 - never block boot on seeding
            logger.warning(
                "Job role seeding skipped (%s). Run `alembic upgrade head` first.", exc
            )

    yield

    await engine.dispose()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description=DESCRIPTION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    @app.get("/", tags=["meta"], summary="Service metadata")
    async def root() -> dict:
        return {
            "service": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "docs": "/docs",
            "api": settings.API_V1_PREFIX,
        }

    return app


app = create_app()
