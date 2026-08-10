"""Liveness and readiness probes."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DbSession
from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.common import HealthResponse

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.PROJECT_NAME,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        database="not_checked",
    )


@router.get("/health/ready", response_model=HealthResponse, summary="Readiness probe")
async def readiness(session: DbSession) -> HealthResponse:
    """Verifies the database connection; used by orchestrators before routing traffic."""
    try:
        await session.execute(text("SELECT 1"))
        database = "connected"
        status_value = "ok"
    except Exception as exc:  # noqa: BLE001 - probe must report, not raise
        logger.error("Readiness DB check failed: %s", exc)
        database = "unavailable"
        status_value = "degraded"

    return HealthResponse(
        status=status_value,
        service=settings.PROJECT_NAME,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        database=database,
    )
