"""Unit tests for the parsing orchestration service.

These call `parse_resume` / `parse_job_description` directly against the test
database (via the `parsing_env` fixture) with a `fake_llm` standing in for
Groq — no HTTP layer, no network, no real API key.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.candidate import Candidate
from app.models.enums import BatchStatus, ParseStatus, UploadSource
from app.models.job_description import JobDescription
from app.models.job_role import JobRole
from app.models.resume import Resume
from app.schemas.parsed_job_description import ParsedJobDescriptionData
from app.schemas.parsed_resume import EducationEntry, ExperienceEntry, ParsedResumeData
from app.services import parsing_service
from app.services.llm import LLMExtractionError
from app.services.storage import compute_content_hash
from app.services.text_extraction import TextExtractionError


async def _make_resume(session, parsing_env, content: bytes, extension: str = ".txt") -> Resume:
    job_role = (await session.execute(select(JobRole).limit(1))).scalar_one()
    stored_filename, relative_path = await parsing_env.save(content, extension)

    resume = Resume(
        job_role_id=job_role.id,
        upload_source=UploadSource.CANDIDATE,
        original_filename=f"cv{extension}",
        stored_filename=stored_filename,
        storage_path=relative_path,
        file_extension=extension,
        content_type="text/plain",
        file_size_bytes=len(content),
        content_hash=compute_content_hash(content),
    )
    session.add(resume)
    await session.commit()
    return resume


class TestParseResumeSuccess:
    async def test_extracts_text_and_stores_structured_data(
        self, session, parsing_env, fake_llm
    ) -> None:
        content = b"RAHUL SHARMA\nAI Engineer\nSkills: Python, RAG"
        resume = await _make_resume(session, parsing_env, content)

        fake_llm.response = ParsedResumeData(
            full_name="Rahul Sharma",
            email="rahul@example.com",
            skills=["Python", "RAG"],
            total_experience_years=4,
            experience=[ExperienceEntry(title="AI Engineer", company="Acme")],
            education=[EducationEntry(degree="B.Tech", institution="VIT")],
        )

        await parsing_service.parse_resume(resume.id)
        await session.refresh(resume)

        assert resume.parse_status == ParseStatus.PARSED
        assert resume.parse_error is None
        assert resume.parsed_at is not None
        assert resume.raw_text == content.decode()
        assert resume.word_count == len(content.decode().split())
        assert resume.parsed_data["full_name"] == "Rahul Sharma"
        assert resume.parsed_data["skills"] == ["Python", "RAG"]
        assert resume.parsed_data["experience"][0]["company"] == "Acme"

    async def test_creates_and_links_a_candidate(self, session, parsing_env, fake_llm) -> None:
        resume = await _make_resume(session, parsing_env, b"JANE DOE\nData Scientist")
        fake_llm.response = ParsedResumeData(
            full_name="Jane Doe", email="jane@example.com", total_experience_years=3.5
        )

        await parsing_service.parse_resume(resume.id)
        await session.refresh(resume)

        assert resume.candidate_id is not None
        candidate = await session.get(Candidate, resume.candidate_id)
        assert candidate.full_name == "Jane Doe"
        assert candidate.email == "jane@example.com"
        assert candidate.total_experience_years == 3.5

    async def test_reparsing_updates_the_same_candidate_not_a_new_one(
        self, session, parsing_env, fake_llm
    ) -> None:
        resume = await _make_resume(session, parsing_env, b"JOHN SMITH\nEngineer")
        fake_llm.response = ParsedResumeData(full_name="John Smith")
        await parsing_service.parse_resume(resume.id)
        await session.refresh(resume)
        first_candidate_id = resume.candidate_id

        fake_llm.response = ParsedResumeData(full_name="John Q. Smith")
        await parsing_service.parse_resume(resume.id)
        await session.refresh(resume)

        assert resume.candidate_id == first_candidate_id
        candidate = await session.get(Candidate, resume.candidate_id)
        assert candidate.full_name == "John Q. Smith"

    async def test_calls_llm_with_the_expected_tool_contract(
        self, session, parsing_env, fake_llm
    ) -> None:
        resume = await _make_resume(session, parsing_env, b"some resume text")
        await parsing_service.parse_resume(resume.id)

        assert len(fake_llm.calls) == 1
        assert fake_llm.calls[0]["tool_name"] == "extract_resume"
        assert "some resume text" in fake_llm.calls[0]["user_content"]


class TestParseResumeFailure:
    async def test_text_extraction_failure_marks_failed_without_calling_llm(
        self, session, parsing_env, fake_llm
    ) -> None:
        resume = await _make_resume(session, parsing_env, b"%PDF-not-real", extension=".pdf")

        await parsing_service.parse_resume(resume.id)
        await session.refresh(resume)

        assert resume.parse_status == ParseStatus.FAILED
        assert resume.parse_error is not None
        assert resume.candidate_id is None
        assert fake_llm.calls == []

    async def test_llm_failure_marks_failed_with_error_message(
        self, session, parsing_env, fake_llm
    ) -> None:
        resume = await _make_resume(session, parsing_env, b"a perfectly readable resume")
        fake_llm.error = LLMExtractionError("Groq is down")

        await parsing_service.parse_resume(resume.id)
        await session.refresh(resume)

        assert resume.parse_status == ParseStatus.FAILED
        assert "Groq is down" in resume.parse_error
        assert resume.candidate_id is None
        # Text extraction still ran and was persisted even though the LLM step failed.
        assert resume.raw_text == "a perfectly readable resume"

    async def test_missing_resume_id_is_a_noop(self, session, parsing_env, fake_llm) -> None:
        await parsing_service.parse_resume(uuid.uuid4())  # must not raise
        assert fake_llm.calls == []

    async def test_unexpected_exception_is_contained(
        self, session, parsing_env, fake_llm
    ) -> None:
        resume = await _make_resume(session, parsing_env, b"some text")
        fake_llm.error = RuntimeError("boom")

        await parsing_service.parse_resume(resume.id)  # must not propagate
        await session.refresh(resume)

        assert resume.parse_status == ParseStatus.FAILED
        assert "boom" in resume.parse_error


class TestParseJobDescription:
    async def _make_jd(self, session, raw_text: str) -> JobDescription:
        jd = JobDescription(title="AI Engineer", raw_text=raw_text)
        session.add(jd)
        await session.commit()
        return jd

    async def test_success_stores_structured_data(self, session, parsing_env, fake_llm) -> None:
        jd = await self._make_jd(session, "Looking for a Python developer with SQL experience.")
        fake_llm.response = ParsedJobDescriptionData(
            required_skills=["Python", "SQL"],
            preferred_skills=["Docker"],
            min_experience_years=2,
        )

        await parsing_service.parse_job_description(jd.id)
        await session.refresh(jd)

        assert jd.parse_status == ParseStatus.PARSED
        assert jd.parsed_data["required_skills"] == ["Python", "SQL"]
        assert jd.parsed_at is not None

    async def test_failure_marks_failed(self, session, parsing_env, fake_llm) -> None:
        jd = await self._make_jd(session, "Some job text")
        fake_llm.error = LLMExtractionError("timeout")

        await parsing_service.parse_job_description(jd.id)
        await session.refresh(jd)

        assert jd.parse_status == ParseStatus.FAILED
        assert "timeout" in jd.parse_error

    async def test_missing_job_description_id_is_a_noop(
        self, session, parsing_env, fake_llm
    ) -> None:
        await parsing_service.parse_job_description(uuid.uuid4())
        assert fake_llm.calls == []
