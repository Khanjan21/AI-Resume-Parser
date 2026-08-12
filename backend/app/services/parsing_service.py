"""Orchestrates parsing: local text extraction, then LLM structured extraction.

Both entry points (`parse_resume`, `parse_job_description`) take an ID and open
their own database session rather than reusing the caller's. They're designed
to run as FastAPI `BackgroundTasks` — by the time one executes, the request
that queued it has already returned its response and closed its own session,
so this function must be self-contained.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.candidate import Candidate
from app.models.enums import ParseStatus
from app.models.job_description import JobDescription
from app.models.resume import Resume
from app.schemas.parsed_job_description import (
    JOB_DESCRIPTION_TOOL_DESCRIPTION,
    JOB_DESCRIPTION_TOOL_NAME,
    ParsedJobDescriptionData,
)
from app.schemas.parsed_resume import (
    RESUME_TOOL_DESCRIPTION,
    RESUME_TOOL_NAME,
    ParsedResumeData,
)
from app.services.llm import LLMExtractionError, get_llm_provider
from app.services.scoring_service import score_resume
from app.services.storage import resume_storage
from app.services.text_extraction import TextExtractionError, extract_text

logger = get_logger(__name__)

_RESUME_SYSTEM_PROMPT = (
    "You are a resume parser. Read the resume text and call the "
    f"{RESUME_TOOL_NAME} tool with the structured data it asks for. "
    "Extract only what the text actually says — use null or an empty list "
    "for anything not present. Normalise skill names to their common form "
    "(e.g. 'PyTorch', 'PostgreSQL', 'React'). If experience dates are given, "
    "estimate total_experience_years from the work history."
)

_JOB_DESCRIPTION_SYSTEM_PROMPT = (
    "You are a job description parser. Read the job description text and "
    f"call the {JOB_DESCRIPTION_TOOL_NAME} tool with the structured data it "
    "asks for. Separate explicitly required skills from merely preferred or "
    "nice-to-have ones. Use null or an empty list for anything not present."
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _sync_candidate(session, resume: Resume, parsed: ParsedResumeData) -> None:
    """Create or refresh the Candidate row a resume's parse links to.

    Overwrites with the latest extraction on every (re-)parse — the resume
    file is the source of truth, not whatever a previous parse guessed.
    """
    if resume.candidate_id is not None:
        candidate = await session.get(Candidate, resume.candidate_id)
    else:
        candidate = Candidate()
        session.add(candidate)
        await session.flush()
        resume.candidate_id = candidate.id

    candidate.full_name = parsed.full_name
    candidate.email = parsed.email
    candidate.phone = parsed.phone
    candidate.location = parsed.location
    candidate.linkedin_url = parsed.linkedin_url
    candidate.github_url = parsed.github_url
    candidate.portfolio_url = parsed.portfolio_url
    candidate.current_title = parsed.current_title
    candidate.total_experience_years = parsed.total_experience_years


async def parse_resume(resume_id: uuid.UUID) -> None:
    parsed_successfully = False

    async with AsyncSessionLocal() as session:
        resume = await session.get(Resume, resume_id)
        if resume is None:
            logger.warning("parse_resume: resume %s no longer exists", resume_id)
            return

        resume.parse_status = ParseStatus.PROCESSING
        await session.commit()

        try:
            content = await resume_storage.read(resume.storage_path)
            extracted = extract_text(content, resume.file_extension)
            resume.raw_text = extracted.text
            resume.page_count = extracted.page_count
            resume.word_count = extracted.word_count

            provider = get_llm_provider()
            parsed = await provider.extract(
                system_prompt=_RESUME_SYSTEM_PROMPT,
                user_content=extracted.text,
                response_model=ParsedResumeData,
                tool_name=RESUME_TOOL_NAME,
                tool_description=RESUME_TOOL_DESCRIPTION,
            )

            resume.parsed_data = parsed.model_dump(mode="json")
            await _sync_candidate(session, resume, parsed)

            resume.parse_status = ParseStatus.PARSED
            resume.parse_error = None
            resume.parsed_at = _utcnow()
            parsed_successfully = True

        except (TextExtractionError, LLMExtractionError) as exc:
            logger.info("Parse failed for resume %s: %s", resume_id, exc)
            resume.parse_status = ParseStatus.FAILED
            resume.parse_error = str(exc)[:2000]

        except Exception as exc:  # noqa: BLE001 - a bad resume must not crash the worker
            logger.exception("Unexpected parse failure for resume %s", resume_id)
            resume.parse_status = ParseStatus.FAILED
            resume.parse_error = f"Unexpected error: {exc}"[:2000]

        await session.commit()

    # Scoring needs its own fresh session — done outside the `async with`
    # block above so parsing's session is fully closed first. A resume that
    # failed to parse has nothing to score yet, so it's left at whatever
    # analysis_status it already had (normally "pending").
    if parsed_successfully:
        await score_resume(resume_id)


async def parse_job_description(job_description_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as session:
        jd = await session.get(JobDescription, job_description_id)
        if jd is None:
            logger.warning(
                "parse_job_description: %s no longer exists", job_description_id
            )
            return

        jd.parse_status = ParseStatus.PROCESSING
        await session.commit()

        try:
            provider = get_llm_provider()
            parsed = await provider.extract(
                system_prompt=_JOB_DESCRIPTION_SYSTEM_PROMPT,
                user_content=jd.raw_text,
                response_model=ParsedJobDescriptionData,
                tool_name=JOB_DESCRIPTION_TOOL_NAME,
                tool_description=JOB_DESCRIPTION_TOOL_DESCRIPTION,
            )

            jd.parsed_data = parsed.model_dump(mode="json")
            jd.parse_status = ParseStatus.PARSED
            jd.parse_error = None
            jd.parsed_at = _utcnow()

        except LLMExtractionError as exc:
            logger.info("Parse failed for job description %s: %s", job_description_id, exc)
            jd.parse_status = ParseStatus.FAILED
            jd.parse_error = str(exc)[:2000]

        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected parse failure for job description %s", job_description_id)
            jd.parse_status = ParseStatus.FAILED
            jd.parse_error = f"Unexpected error: {exc}"[:2000]

        await session.commit()
