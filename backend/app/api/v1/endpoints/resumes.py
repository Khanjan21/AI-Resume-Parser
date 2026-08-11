"""Candidate-flow resume upload plus shared resume operations."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, File, Form, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from app.api.deps import (
    DbSession,
    PaginationDep,
    get_job_role_or_404,
    get_resume_or_404,
)
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.models.enums import ParseStatus, UploadSource
from app.models.resume import Resume
from app.schemas.common import MessageResponse, Page, PageMeta
from app.schemas.resume import ResumeRead, ResumeUploadResponse
from app.services import resume_service
from app.services.parsing_service import parse_resume
from app.services.storage import resume_storage


def _queue_parse(background_tasks: BackgroundTasks, resume_id: uuid.UUID) -> None:
    if settings.PARSE_ON_UPLOAD and settings.GROQ_API_KEY:
        background_tasks.add_task(parse_resume, resume_id)

router = APIRouter(prefix="/resumes", tags=["resumes"])


@router.post(
    "",
    response_model=ResumeUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a single resume for a job role (candidate flow)",
)
async def upload_resume(
    session: DbSession,
    background_tasks: BackgroundTasks,
    job_role_id: uuid.UUID = Form(..., description="Target job role"),
    file: UploadFile = File(..., description="PDF, DOCX, TXT or MD, max 10 MB"),
) -> ResumeUploadResponse:
    """Stores the file and queues it for parsing.

    Re-uploading the same bytes for the same role returns the existing record
    instead of creating a second copy (and is not re-queued for parsing).
    """
    await get_job_role_or_404(session, job_role_id)

    try:
        resume, duplicate = await resume_service.ingest_resume(
            session,
            file=file,
            job_role_id=job_role_id,
            upload_source=UploadSource.CANDIDATE,
        )
    finally:
        await file.close()

    if not duplicate:
        _queue_parse(background_tasks, resume.id)

    return ResumeUploadResponse(
        resume=ResumeRead.model_validate(resume),
        duplicate=duplicate,
        message=(
            "This resume was already uploaded for this role; returning the existing record."
            if duplicate
            else "Resume uploaded successfully and queued for parsing."
        ),
    )


@router.get("", response_model=Page[ResumeRead], summary="List resumes")
async def list_resumes(
    session: DbSession,
    pagination: PaginationDep,
    job_role_id: uuid.UUID | None = Query(default=None),
    batch_id: uuid.UUID | None = Query(default=None),
    upload_source: UploadSource | None = Query(default=None),
    parse_status: ParseStatus | None = Query(default=None),
) -> Page[ResumeRead]:
    filters = []
    if job_role_id:
        filters.append(Resume.job_role_id == job_role_id)
    if batch_id:
        filters.append(Resume.batch_id == batch_id)
    if upload_source:
        filters.append(Resume.upload_source == upload_source)
    if parse_status:
        filters.append(Resume.parse_status == parse_status)

    total = await session.scalar(select(func.count()).select_from(Resume).where(*filters))

    stmt = (
        select(Resume)
        .where(*filters)
        .order_by(Resume.created_at.desc())
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    resumes = (await session.execute(stmt)).scalars().all()

    return Page[ResumeRead](
        items=[ResumeRead.model_validate(item) for item in resumes],
        meta=PageMeta(
            total=total or 0,
            limit=pagination.limit,
            offset=pagination.offset,
            has_more=pagination.offset + len(resumes) < (total or 0),
        ),
    )


@router.get("/{resume_id}", response_model=ResumeRead, summary="Get a resume record")
async def get_resume(resume_id: uuid.UUID, session: DbSession) -> ResumeRead:
    resume = await get_resume_or_404(session, resume_id)
    return ResumeRead.model_validate(resume)


@router.get("/{resume_id}/download", summary="Download the original file")
async def download_resume(resume_id: uuid.UUID, session: DbSession) -> FileResponse:
    resume = await get_resume_or_404(session, resume_id)

    if not resume_storage.exists(resume.storage_path):
        raise NotFoundError("The stored file for this resume is missing.")

    return FileResponse(
        path=resume_storage.absolute_path(resume.storage_path),
        media_type=resume.content_type,
        filename=resume.original_filename,
    )


@router.post(
    "/{resume_id}/parse",
    response_model=ResumeRead,
    summary="(Re-)run text extraction and structured parsing on a resume",
)
async def reparse_resume(
    resume_id: uuid.UUID,
    session: DbSession,
    background_tasks: BackgroundTasks,
) -> ResumeRead:
    resume = await get_resume_or_404(session, resume_id)
    resume.parse_status = ParseStatus.PENDING
    await session.flush()
    # `updated_at` is server-computed (onupdate=func.now()); after an UPDATE,
    # SQLAlchemy marks it expired rather than eagerly re-fetching it the way
    # it does for INSERTs via RETURNING. Refresh before serializing or
    # Pydantic's attribute access triggers an implicit lazy-load outside any
    # awaited context, raising MissingGreenlet.
    await session.refresh(resume)
    background_tasks.add_task(parse_resume, resume.id)
    return ResumeRead.model_validate(resume)


@router.delete(
    "/{resume_id}",
    response_model=MessageResponse,
    summary="Delete a resume and its stored file",
)
async def delete_resume(resume_id: uuid.UUID, session: DbSession) -> MessageResponse:
    resume = await get_resume_or_404(session, resume_id)
    await resume_service.delete_resume(session, resume)
    return MessageResponse(message="Resume deleted.")
