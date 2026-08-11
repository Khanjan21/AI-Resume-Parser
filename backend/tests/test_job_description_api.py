"""API tests for job-description creation and parsing."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from tests.conftest import FakeLLMProvider


class TestCreateJobDescription:
    async def test_creates_from_pasted_text_and_queues_parsing(
        self, client: AsyncClient, fake_llm: FakeLLMProvider
    ) -> None:
        response = await client.post(
            "/api/v1/job-descriptions",
            data={
                "title": "AI Engineer",
                "company": "Acme Corp",
                "raw_text": "We need someone strong in Python and RAG systems.",
            },
        )
        assert response.status_code == 201

        body = response.json()
        assert body["title"] == "AI Engineer"
        assert body["company"] == "Acme Corp"
        assert body["source_filename"] is None

        # Background parsing already ran (ASGI transport awaits it inline).
        assert len(fake_llm.calls) == 1
        assert fake_llm.calls[0]["tool_name"] == "extract_job_description"

        detail = await client.get(f"/api/v1/job-descriptions/{body['id']}")
        assert detail.json()["parse_status"] == "parsed"

    async def test_creates_from_an_uploaded_file(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/job-descriptions",
            data={"title": "Data Scientist"},
            files={"file": ("jd.txt", b"Must know Python, SQL and statistics.", "text/plain")},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["source_filename"] == "jd.txt"

        detail = await client.get(f"/api/v1/job-descriptions/{body['id']}")
        assert "Python" in detail.json()["raw_text"]

    async def test_rejects_neither_text_nor_file(self, client: AsyncClient) -> None:
        response = await client.post("/api/v1/job-descriptions", data={"title": "x"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    async def test_rejects_both_text_and_file(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/job-descriptions",
            data={"title": "x", "raw_text": "some text"},
            files={"file": ("jd.txt", b"more text", "text/plain")},
        )
        assert response.status_code == 422

    async def test_rejects_blank_raw_text(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/job-descriptions", data={"title": "x", "raw_text": "   "}
        )
        assert response.status_code == 422

    async def test_links_to_a_job_role(self, client: AsyncClient, ai_role_id: str) -> None:
        response = await client.post(
            "/api/v1/job-descriptions",
            data={"title": "AI Engineer", "job_role_id": ai_role_id, "raw_text": "Python and RAG."},
        )
        assert response.status_code == 201
        assert response.json()["job_role_id"] == ai_role_id


class TestJobDescriptionRetrieval:
    async def test_lists_and_filters_by_role(
        self, client: AsyncClient, ai_role_id: str
    ) -> None:
        await client.post(
            "/api/v1/job-descriptions",
            data={"title": "AI Engineer", "job_role_id": ai_role_id, "raw_text": "Python."},
        )
        await client.post(
            "/api/v1/job-descriptions", data={"title": "Unrelated", "raw_text": "Something."}
        )

        filtered = await client.get(
            "/api/v1/job-descriptions", params={"job_role_id": ai_role_id}
        )
        assert filtered.json()["meta"]["total"] == 1

        unfiltered = await client.get("/api/v1/job-descriptions")
        assert unfiltered.json()["meta"]["total"] == 2

    async def test_unknown_id_returns_404(self, client: AsyncClient) -> None:
        response = await client.get(f"/api/v1/job-descriptions/{uuid.uuid4()}")
        assert response.status_code == 404


class TestReparse:
    async def test_reparse_endpoint_reruns_extraction(
        self, client: AsyncClient, fake_llm: FakeLLMProvider
    ) -> None:
        created = await client.post(
            "/api/v1/job-descriptions", data={"title": "x", "raw_text": "Python required."}
        )
        jd_id = created.json()["id"]
        assert len(fake_llm.calls) == 1

        response = await client.post(f"/api/v1/job-descriptions/{jd_id}/parse")
        assert response.status_code == 200
        assert len(fake_llm.calls) == 2

    async def test_reparse_unknown_id_returns_404(self, client: AsyncClient) -> None:
        response = await client.post(f"/api/v1/job-descriptions/{uuid.uuid4()}/parse")
        assert response.status_code == 404
