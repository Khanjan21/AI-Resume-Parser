"""Health and metadata endpoints."""

from __future__ import annotations

from httpx import AsyncClient


async def test_liveness(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_readiness_reports_database(client: AsyncClient) -> None:
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["database"] == "connected"


async def test_root_exposes_metadata(client: AsyncClient) -> None:
    body = (await client.get("/")).json()
    assert body["api"] == "/api/v1"
    assert body["docs"] == "/docs"


async def test_openapi_schema_is_generated(client: AsyncClient) -> None:
    schema = (await client.get("/openapi.json")).json()
    assert "/api/v1/job-roles" in schema["paths"]
    assert "/api/v1/batches/{batch_id}/resumes" in schema["paths"]
