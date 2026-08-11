"""Confirms upload endpoints actually queue and complete background parsing.

Under httpx's ASGITransport, FastAPI's BackgroundTasks run to completion
before the response is returned to the test, so these assertions don't need
to poll or sleep — by the time `await client.post(...)` returns, the parse
already happened against the (fake) LLM.
"""

from __future__ import annotations

from httpx import AsyncClient

from app.schemas.parsed_resume import ParsedResumeData
from tests.conftest import FakeLLMProvider


class TestCandidateUploadTriggersParsing:
    async def test_upload_queues_and_completes_a_parse(
        self, client: AsyncClient, ai_role_id: str, fake_llm: FakeLLMProvider
    ) -> None:
        fake_llm.response = ParsedResumeData(full_name="Priya Nair", skills=["React", "Node.js"])

        upload = await client.post(
            "/api/v1/resumes",
            data={"job_role_id": ai_role_id},
            files={"file": ("priya.txt", b"PRIYA NAIR\nReact, Node.js", "text/plain")},
        )
        resume_id = upload.json()["resume"]["id"]

        # The immediate response always reflects pre-parse state.
        assert upload.json()["resume"]["parse_status"] == "pending"

        detail = await client.get(f"/api/v1/resumes/{resume_id}")
        body = detail.json()
        assert body["parse_status"] == "parsed"
        assert body["word_count"] > 0

    async def test_duplicate_upload_is_not_re_parsed(
        self, client: AsyncClient, ai_role_id: str, fake_llm: FakeLLMProvider
    ) -> None:
        files = {"file": ("dup.txt", b"same bytes every time", "text/plain")}
        await client.post("/api/v1/resumes", data={"job_role_id": ai_role_id}, files=files)
        assert len(fake_llm.calls) == 1

        await client.post("/api/v1/resumes", data={"job_role_id": ai_role_id}, files=files)
        assert len(fake_llm.calls) == 1  # still one — the duplicate wasn't re-queued

    async def test_manual_reparse_endpoint(
        self, client: AsyncClient, ai_role_id: str, fake_llm: FakeLLMProvider
    ) -> None:
        upload = await client.post(
            "/api/v1/resumes",
            data={"job_role_id": ai_role_id},
            files={"file": ("cv.txt", b"some resume content", "text/plain")},
        )
        resume_id = upload.json()["resume"]["id"]
        assert len(fake_llm.calls) == 1

        response = await client.post(f"/api/v1/resumes/{resume_id}/parse")
        assert response.status_code == 200
        assert len(fake_llm.calls) == 2


class TestBulkUploadTriggersParsing:
    async def test_each_uploaded_file_is_parsed_but_not_rejected_ones(
        self, client: AsyncClient, ai_role_id: str, fake_llm: FakeLLMProvider
    ) -> None:
        batch = await client.post(
            "/api/v1/batches", json={"job_role_id": ai_role_id, "name": "batch"}
        )
        batch_id = batch.json()["id"]

        response = await client.post(
            f"/api/v1/batches/{batch_id}/resumes",
            files=[
                ("files", ("a.txt", b"resume A content", "text/plain")),
                ("files", ("b.txt", b"resume B content", "text/plain")),
                ("files", ("bad.pdf", b"not a real pdf", "application/pdf")),
            ],
        )
        body = response.json()
        assert body["uploaded"] == 2
        assert body["rejected"] == 1

        # Only the two successfully uploaded files were queued for parsing.
        assert len(fake_llm.calls) == 2

    async def test_duplicate_within_a_batch_is_not_re_parsed(
        self, client: AsyncClient, ai_role_id: str, fake_llm: FakeLLMProvider
    ) -> None:
        batch = await client.post(
            "/api/v1/batches", json={"job_role_id": ai_role_id, "name": "batch"}
        )
        batch_id = batch.json()["id"]

        same_file = ("files", ("dup.txt", b"identical content", "text/plain"))
        await client.post(f"/api/v1/batches/{batch_id}/resumes", files=[same_file, same_file])

        assert len(fake_llm.calls) == 1
