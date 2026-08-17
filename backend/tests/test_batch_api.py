"""API tests for the recruiter bulk-screening flow."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from app.core.config import settings
from app.schemas.parsed_resume import ParsedResumeData
from tests.conftest import FakeLLMProvider


def multi_files(*items: tuple[str, bytes, str]) -> list[tuple[str, tuple]]:
    return [("files", item) for item in items]


VALID_A = ("amit.txt", b"AMIT VERMA\nML Engineer\nPython, PyTorch, MLflow", "text/plain")
VALID_B = ("priya.txt", b"PRIYA NAIR\nFull Stack\nReact, Node.js, PostgreSQL", "text/plain")
FAKE_PDF = ("fake.pdf", b"not a pdf", "application/pdf")


class TestCreateBatch:
    async def test_creates_a_batch(self, client: AsyncClient, ai_role_id: str) -> None:
        response = await client.post(
            "/api/v1/batches",
            json={
                "job_role_id": ai_role_id,
                "name": "Q3 AI hiring",
                "recruiter_email": "hiring@example.com",
            },
        )
        assert response.status_code == 201

        body = response.json()
        assert body["status"] == "created"
        assert body["total_resumes"] == 0

    async def test_rejects_unknown_role(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/batches", json={"job_role_id": str(uuid.uuid4()), "name": "x"}
        )
        assert response.status_code == 404

    async def test_links_a_job_description(
        self, client: AsyncClient, ai_role_id: str
    ) -> None:
        jd = await client.post(
            "/api/v1/job-descriptions",
            data={"title": "AI Engineer", "raw_text": "Need Python and RAG experience."},
        )
        jd_id = jd.json()["id"]

        response = await client.post(
            "/api/v1/batches",
            json={
                "job_role_id": ai_role_id,
                "job_description_id": jd_id,
                "name": "with JD",
            },
        )
        assert response.status_code == 201
        assert response.json()["job_description_id"] == jd_id

    async def test_rejects_unknown_job_description(
        self, client: AsyncClient, ai_role_id: str
    ) -> None:
        response = await client.post(
            "/api/v1/batches",
            json={
                "job_role_id": ai_role_id,
                "job_description_id": str(uuid.uuid4()),
                "name": "x",
            },
        )
        assert response.status_code == 404

    async def test_rejects_invalid_email(
        self, client: AsyncClient, ai_role_id: str
    ) -> None:
        response = await client.post(
            "/api/v1/batches",
            json={"job_role_id": ai_role_id, "name": "x", "recruiter_email": "nope"},
        )
        assert response.status_code == 422


class TestBulkUpload:
    async def _batch(self, client: AsyncClient, role_id: str) -> str:
        response = await client.post(
            "/api/v1/batches", json={"job_role_id": role_id, "name": "bulk"}
        )
        return response.json()["id"]

    async def test_uploads_multiple_resumes(
        self, client: AsyncClient, ai_role_id: str
    ) -> None:
        batch_id = await self._batch(client, ai_role_id)

        response = await client.post(
            f"/api/v1/batches/{batch_id}/resumes",
            files=multi_files(VALID_A, VALID_B),
        )
        assert response.status_code == 201

        body = response.json()
        assert body["received"] == 2
        assert body["uploaded"] == 2
        assert body["rejected"] == 0
        assert all(item["status"] == "uploaded" for item in body["items"])

    async def test_reports_bad_files_without_failing_the_batch(
        self, client: AsyncClient, ai_role_id: str
    ) -> None:
        """One malformed CV must not cost the recruiter the other 49."""
        batch_id = await self._batch(client, ai_role_id)

        response = await client.post(
            f"/api/v1/batches/{batch_id}/resumes",
            files=multi_files(VALID_A, FAKE_PDF, VALID_B),
        )
        assert response.status_code == 201

        body = response.json()
        assert body["uploaded"] == 2
        assert body["rejected"] == 1

        rejected = next(i for i in body["items"] if i["status"] == "rejected")
        assert rejected["filename"] == "fake.pdf"
        assert rejected["error_code"] == "unsupported_file_type"

    async def test_deduplicates_within_a_batch(
        self, client: AsyncClient, ai_role_id: str
    ) -> None:
        batch_id = await self._batch(client, ai_role_id)

        response = await client.post(
            f"/api/v1/batches/{batch_id}/resumes",
            files=multi_files(VALID_A, VALID_A),
        )
        body = response.json()

        assert body["uploaded"] == 1
        assert body["duplicates"] == 1

    async def test_updates_batch_counters_and_status(
        self, client: AsyncClient, ai_role_id: str
    ) -> None:
        batch_id = await self._batch(client, ai_role_id)
        await client.post(
            f"/api/v1/batches/{batch_id}/resumes", files=multi_files(VALID_A, VALID_B)
        )

        detail = (await client.get(f"/api/v1/batches/{batch_id}")).json()
        assert detail["total_resumes"] == 2
        assert detail["status"] == "uploading"
        assert len(detail["resumes"]) == 2
        assert detail["job_role"]["slug"] == "ai-engineer"

    async def test_rejects_more_files_than_the_limit(
        self, client: AsyncClient, ai_role_id: str, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            "app.api.v1.endpoints.batches.settings.MAX_BULK_UPLOAD_FILES", 2
        )
        batch_id = await self._batch(client, ai_role_id)

        response = await client.post(
            f"/api/v1/batches/{batch_id}/resumes",
            files=multi_files(VALID_A, VALID_B, ("c.txt", b"third resume", "text/plain")),
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    async def test_unknown_batch_returns_404(self, client: AsyncClient) -> None:
        response = await client.post(
            f"/api/v1/batches/{uuid.uuid4()}/resumes", files=multi_files(VALID_A)
        )
        assert response.status_code == 404


class TestBatchLifecycle:
    async def test_lists_and_filters_batches(
        self, client: AsyncClient, ai_role_id: str
    ) -> None:
        await client.post(
            "/api/v1/batches", json={"job_role_id": ai_role_id, "name": "one"}
        )

        listed = await client.get("/api/v1/batches", params={"job_role_id": ai_role_id})
        assert listed.json()["meta"]["total"] == 1

        empty = await client.get("/api/v1/batches", params={"status": "completed"})
        assert empty.json()["meta"]["total"] == 0

    async def test_deleting_a_batch_removes_its_resumes(
        self, client: AsyncClient, ai_role_id: str
    ) -> None:
        created = await client.post(
            "/api/v1/batches", json={"job_role_id": ai_role_id, "name": "doomed"}
        )
        batch_id = created.json()["id"]
        upload = await client.post(
            f"/api/v1/batches/{batch_id}/resumes", files=multi_files(VALID_A)
        )
        resume_id = upload.json()["items"][0]["resume_id"]

        assert (await client.delete(f"/api/v1/batches/{batch_id}")).status_code == 200
        assert (await client.get(f"/api/v1/batches/{batch_id}")).status_code == 404
        assert (await client.get(f"/api/v1/resumes/{resume_id}")).status_code == 404


class TestBatchRanking:
    """Day 5: resumes come back ranked by `final_score`, bucketed into a
    shortlist category, with batch-level counts per category."""

    async def _custom_role(self, client: AsyncClient) -> str:
        # Weighting only `required_skills` makes `final_score` a pure,
        # predictable function of skill overlap — untouched by ATS keyword
        # scanning or the semantic embedding, so category boundaries land
        # exactly where the test expects.
        response = await client.post(
            "/api/v1/job-roles",
            json={
                "title": "Ranking Test Role",
                "required_skills": ["Alpha", "Beta"],
                "scoring_weights": {"required_skills": 1.0},
            },
        )
        return response.json()["id"]

    async def _upload_one(
        self, client: AsyncClient, batch_id: str, fake_llm: FakeLLMProvider, filename: str, skills: list[str]
    ) -> None:
        fake_llm.response = ParsedResumeData(skills=skills)
        # Distinct bytes per file — de-duplication is content-hash based and
        # scoped to the batch, so identical bodies would collide as
        # "duplicate" regardless of filename.
        await client.post(
            f"/api/v1/batches/{batch_id}/resumes",
            files=[("files", (filename, f"resume content for {filename}".encode(), "text/plain"))],
        )

    async def test_resumes_are_ranked_by_final_score_descending(
        self, client: AsyncClient, fake_llm: FakeLLMProvider
    ) -> None:
        role_id = await self._custom_role(client)
        batch = await client.post(
            "/api/v1/batches", json={"job_role_id": role_id, "name": "ranking"}
        )
        batch_id = batch.json()["id"]

        # Uploaded out of score order on purpose, to prove the response is
        # actually sorted rather than just echoing upload order.
        await self._upload_one(client, batch_id, fake_llm, "weak.txt", [])
        await self._upload_one(client, batch_id, fake_llm, "strong.txt", ["Alpha", "Beta"])
        await self._upload_one(client, batch_id, fake_llm, "consider.txt", ["Alpha"])

        detail = (await client.get(f"/api/v1/batches/{batch_id}")).json()

        filenames = [r["original_filename"] for r in detail["resumes"]]
        assert filenames == ["strong.txt", "consider.txt", "weak.txt"]

        scores = [r["score"]["final_score"] for r in detail["resumes"]]
        assert scores == sorted(scores, reverse=True)

        categories = [r["score"]["category"] for r in detail["resumes"]]
        assert categories == ["strong_match", "consider", "weak_match"]

    async def test_category_counts_reflect_the_batch(
        self, client: AsyncClient, fake_llm: FakeLLMProvider
    ) -> None:
        role_id = await self._custom_role(client)
        batch = await client.post(
            "/api/v1/batches", json={"job_role_id": role_id, "name": "counts"}
        )
        batch_id = batch.json()["id"]

        await self._upload_one(client, batch_id, fake_llm, "a.txt", ["Alpha", "Beta"])
        await self._upload_one(client, batch_id, fake_llm, "b.txt", ["Alpha", "Beta"])
        await self._upload_one(client, batch_id, fake_llm, "c.txt", ["Alpha"])
        await self._upload_one(client, batch_id, fake_llm, "d.txt", [])

        detail = (await client.get(f"/api/v1/batches/{batch_id}")).json()

        assert detail["category_counts"] == {
            "strong_match": 2,
            "consider": 1,
            "weak_match": 1,
            "unscored": 0,
        }

    async def test_unscored_resumes_sort_last_and_count_separately(
        self, client: AsyncClient, ai_role_id: str, fake_llm: FakeLLMProvider, monkeypatch
    ) -> None:
        batch = await client.post(
            "/api/v1/batches", json={"job_role_id": ai_role_id, "name": "mixed"}
        )
        batch_id = batch.json()["id"]

        monkeypatch.setattr(settings, "PARSE_ON_UPLOAD", False)
        await client.post(
            f"/api/v1/batches/{batch_id}/resumes",
            files=[("files", ("unscored.txt", b"resume content", "text/plain"))],
        )

        monkeypatch.setattr(settings, "PARSE_ON_UPLOAD", True)
        await self._upload_one(client, batch_id, fake_llm, "scored.txt", ["Python"])

        detail = (await client.get(f"/api/v1/batches/{batch_id}")).json()

        filenames = [r["original_filename"] for r in detail["resumes"]]
        assert filenames == ["scored.txt", "unscored.txt"]
        assert detail["category_counts"]["unscored"] == 1
