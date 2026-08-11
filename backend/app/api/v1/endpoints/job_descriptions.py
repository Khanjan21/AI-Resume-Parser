"""Recruiter-supplied job descriptions: create (file or pasted text), then parse."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, File, Form, Query, UploadFile, status
from sqlalchemy import func, select

from app.api.deps import DbSession, PaginationDep, get_job_description_or_404
from app.core.config import settings
from app.core.exceptions import ValidationError
from app.models.enums import ParseStatus
from app.models.job_description import JobDescription
from app.schemas.common import Page, PageMeta
from app.schemas.job_description import JobDescriptionDetail, JobDescriptionRead
from app.services.parsing_service import parse_job_description
from app.services.text_extraction import extract_text
from app.services.file_validation import validate_upload

router = APIRouter(prefix="/job-descriptions", tags=["job-descriptions"])


@router.post(
    "",
    response_model=JobDescriptionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a job description from pasted text or an uploaded file",
)
async def create_job_description(
    session: DbSession,
    background_tasks: BackgroundTasks,
    title: str = Form(..., min_length=1, max_length=200),
    company: str | None = Form(default=None, max_length=200),
    location: str | None = Form(default=None, max_length=160),
    job_role_id: uuid.UUID | None = Form(default=None),
    raw_text: str | None = Form(default=None, description="Pasted job description text"),
    file: UploadFile | None = File(default=None),
) -> JobDescriptionRead:
    """Exactly one of `raw_text` or `file` must be provided.

    Unlike resumes, the uploaded file itself isn't kept — only the text
    extracted from it — so there is no download endpoint for job descriptions.
    """
    if bool(raw_text) == bool(file):
        raise ValidationError("Provide exactly one of `raw_text` or `file`.")

    if file is not None:
        validated = await validate_upload(file)
        await file.close()
        extracted = extract_text(validated.content, validated.extension)
        text = extracted.text
        source_filename = validated.original_filename
    else:
        text = (raw_text or "").strip()
        if not text:
            raise ValidationError("`raw_text` cannot be blank.")
        source_filename = None

    jd = JobDescription(
        job_role_id=job_role_id,
        title=title,
        company=company,
        location=location,
        raw_text=text,
        source_filename=source_filename,
        parse_status=ParseStatus.PENDING,
    )
    session.add(jd)
    await session.flush()

    if settings.PARSE_ON_UPLOAD and settings.GROQ_API_KEY:
        background_tasks.add_task(parse_job_description, jd.id)

    return JobDescriptionRead.model_validate(jd)


@router.get("", response_model=Page[JobDescriptionRead], summary="List job descriptions")
async def list_job_descriptions(
    session: DbSession,
    pagination: PaginationDep,
    job_role_id: uuid.UUID | None = Query(default=None),
    parse_status: ParseStatus | None = Query(default=None),
) -> Page[JobDescriptionRead]:
    filters = []
    if job_role_id:
        filters.append(JobDescription.job_role_id == job_role_id)
    if parse_status:
        filters.append(JobDescription.parse_status == parse_status)

    total = await session.scalar(
        select(func.count()).select_from(JobDescription).where(*filters)
    )

    stmt = (
        select(JobDescription)
        .where(*filters)
        .order_by(JobDescription.created_at.desc())
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    items = (await session.execute(stmt)).scalars().all()

    return Page[JobDescriptionRead](
        items=[JobDescriptionRead.model_validate(item) for item in items],
        meta=PageMeta(
            total=total or 0,
            limit=pagination.limit,
            offset=pagination.offset,
            has_more=pagination.offset + len(items) < (total or 0),
        ),
    )


@router.get(
    "/{job_description_id}",
    response_model=JobDescriptionDetail,
    summary="Get a job description, including parsed data",
)
async def get_job_description(
    job_description_id: uuid.UUID, session: DbSession
) -> JobDescriptionDetail:
    jd = await get_job_description_or_404(session, job_description_id)
    return JobDescriptionDetail.model_validate(jd)


@router.post(
    "/{job_description_id}/parse",
    response_model=JobDescriptionRead,
    summary="(Re-)run structured extraction on a job description",
)
async def reparse_job_description(
    job_description_id: uuid.UUID,
    session: DbSession,
    background_tasks: BackgroundTasks,
) -> JobDescriptionRead:
    jd = await get_job_description_or_404(session, job_description_id)
    jd.parse_status = ParseStatus.PENDING
    await session.flush()
    # See the matching comment in resumes.reparse_resume: `updated_at` is
    # server-computed and left expired after an UPDATE, so it must be
    # refreshed before serialization or Pydantic's attribute access raises
    # MissingGreenlet trying to lazy-load it outside an awaited context.
    await session.refresh(jd)
    background_tasks.add_task(parse_job_description, jd.id)
    return JobDescriptionRead.model_validate(jd)
