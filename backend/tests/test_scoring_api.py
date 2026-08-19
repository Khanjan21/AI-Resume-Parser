"""API tests for scoring: score appears on resume/batch detail, manual re-score."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from app.core.config import settings
from app.models.enums import ParseStatus
from app.models.resume import Resume
from app.schemas.parsed_job_description import ParsedJobDescriptionData
from app.schemas.parsed_resume import ParsedResumeData
from tests.conftest import FakeLLMProvider


async def _upload_and_wait(client, role_id, fake_llm, *, skills=None, years=None):
    fake_llm.response = ParsedResumeData(
        full_name="Test Candidate", skills=skills or [], total_experience_years=years
    )
    response = await client.post(
        "/api/v1/resumes",
        data={"job_role_id": role_id},
        files={"file": ("cv.txt", b"resume content", "text/plain")},
    )
    return response.json()["resume"]["id"]


class TestScoreOnResumeDetail:
    async def test_parsed_resume_has_a_score_attached(
        self, client: AsyncClient, ai_role_id: str, fake_llm: FakeLLMProvider
    ) -> None:
        resume_id = await _upload_and_wait(
            client, ai_role_id, fake_llm, skills=["Python", "RAG"], years=4
        )

        detail = (await client.get(f"/api/v1/resumes/{resume_id}")).json()

        assert detail["analysis_status"] == "completed"
        assert detail["score"] is not None
        assert detail["score"]["resume_id"] == resume_id
        assert 0.0 <= detail["score"]["required_skill_match"] <= 100.0
        assert "Python" in detail["score"]["matched_skills"]

    async def test_unparsed_resume_has_no_score_yet(
        self, client: AsyncClient, ai_role_id: str, monkeypatch
    ) -> None:
        # Uploaded with parsing/scoring disabled, so it's genuinely never scored
        # — resetting a scored resume's status afterward wouldn't remove its
        # already-created score row, so this has to start from pending.
        monkeypatch.setattr(settings, "PARSE_ON_UPLOAD", False)

        response = await client.post(
            "/api/v1/resumes",
            data={"job_role_id": ai_role_id},
            files={"file": ("cv.txt", b"resume content", "text/plain")},
        )
        resume_id = response.json()["resume"]["id"]
        assert response.json()["resume"]["parse_status"] == "pending"

        detail = (await client.get(f"/api/v1/resumes/{resume_id}")).json()
        assert detail["score"] is None


class TestCandidateScoringWithJobDescription:
    async def test_candidate_upload_is_scored_against_its_linked_jd(
        self, client: AsyncClient, ai_role_id: str, fake_llm: FakeLLMProvider
    ) -> None:
        jd = await client.post(
            "/api/v1/job-descriptions",
            data={"title": "AI Engineer", "raw_text": "Need Kubernetes experience."},
        )
        fake_llm.response = ParsedJobDescriptionData(required_skills=["Kubernetes"])
        reparsed = await client.post(f"/api/v1/job-descriptions/{jd.json()['id']}/parse")
        jd_id = reparsed.json()["id"]

        fake_llm.response = ParsedResumeData(skills=["Python"])  # no Kubernetes
        upload = await client.post(
            "/api/v1/resumes",
            data={"job_role_id": ai_role_id, "job_description_id": jd_id},
            files={"file": ("with_jd.txt", b"resume content", "text/plain")},
        )

        detail = (await client.get(f"/api/v1/resumes/{upload.json()['resume']['id']}")).json()
        assert detail["job_description_id"] == jd_id
        assert "Kubernetes" in detail["score"]["missing_skills"]


class TestManualRescore:
    async def test_rescore_recomputes_the_score(
        self, client: AsyncClient, ai_role_id: str, fake_llm: FakeLLMProvider
    ) -> None:
        resume_id = await _upload_and_wait(
            client, ai_role_id, fake_llm, skills=["Python"], years=2
        )
        first = (await client.get(f"/api/v1/resumes/{resume_id}")).json()

        response = await client.post(f"/api/v1/resumes/{resume_id}/score")
        assert response.status_code == 200
        second = response.json()

        assert second["score"] is not None
        assert second["score"]["scored_at"] > first["score"]["scored_at"]

    async def test_rejects_scoring_an_unparsed_resume(
        self, client: AsyncClient, ai_role_id: str, fake_llm: FakeLLMProvider, session
    ) -> None:
        resume_id = await _upload_and_wait(client, ai_role_id, fake_llm)

        resume = await session.get(Resume, uuid.UUID(resume_id))
        resume.parse_status = ParseStatus.PENDING
        await session.commit()

        response = await client.post(f"/api/v1/resumes/{resume_id}/score")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    async def test_rescore_unknown_resume_returns_404(self, client: AsyncClient) -> None:
        response = await client.post(f"/api/v1/resumes/{uuid.uuid4()}/score")
        assert response.status_code == 404


class TestScoreOnBatchDetail:
    async def test_batch_resumes_include_scores(
        self, client: AsyncClient, ai_role_id: str, fake_llm: FakeLLMProvider
    ) -> None:
        batch = await client.post(
            "/api/v1/batches", json={"job_role_id": ai_role_id, "name": "batch"}
        )
        batch_id = batch.json()["id"]

        fake_llm.response = ParsedResumeData(skills=["Python"], total_experience_years=3)
        await client.post(
            f"/api/v1/batches/{batch_id}/resumes",
            files=[("files", ("a.txt", b"resume A", "text/plain"))],
        )

        detail = (await client.get(f"/api/v1/batches/{batch_id}")).json()
        assert len(detail["resumes"]) == 1
        assert detail["resumes"][0]["score"] is not None
        assert detail["resumes"][0]["score"]["required_skill_match"] is not None

    async def test_batch_scoring_uses_linked_job_description(
        self, client: AsyncClient, ai_role_id: str, fake_llm: FakeLLMProvider
    ) -> None:
        jd = await client.post(
            "/api/v1/job-descriptions",
            data={"title": "AI Engineer", "raw_text": "Need Kubernetes experience."},
        )
        fake_llm.response = ParsedJobDescriptionData(required_skills=["Kubernetes"])
        reparsed = await client.post(f"/api/v1/job-descriptions/{jd.json()['id']}/parse")
        jd_id = reparsed.json()["id"]

        batch = await client.post(
            "/api/v1/batches",
            json={"job_role_id": ai_role_id, "job_description_id": jd_id, "name": "batch"},
        )
        batch_id = batch.json()["id"]

        fake_llm.response = ParsedResumeData(skills=["Python"])  # no Kubernetes
        await client.post(
            f"/api/v1/batches/{batch_id}/resumes",
            files=[("files", ("a.txt", b"resume A", "text/plain"))],
        )

        detail = (await client.get(f"/api/v1/batches/{batch_id}")).json()
        score = detail["resumes"][0]["score"]
        assert "Kubernetes" in score["missing_skills"]
