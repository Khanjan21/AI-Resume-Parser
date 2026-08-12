"""Recruiter flow: create a screening batch, then bulk-upload resumes into it."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, File, Query, UploadFile, status
from sqlalchemy import func, select

from app.api.deps import (
    DbSession,
    PaginationDep,
    get_batch_or_404,
    get_job_description_or_404,
    get_job_role_or_404,
)
from app.core.config import settings
from app.core.exceptions import ValidationError
from app.models.enums import BatchStatus
from app.models.screening_batch import ScreeningBatch
from app.schemas.batch import BatchCreate, BatchDetail, BatchRead
from app.schemas.common import MessageResponse, Page, PageMeta
from app.schemas.job_role import JobRoleSummary
from app.schemas.resume import BulkUploadResponse, ResumeDetail
from app.services import resume_service
from app.services.parsing_service import parse_resume

router = APIRouter(prefix="/batches", tags=["recruiter-batches"])


@router.post(
    "",
    response_model=BatchRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a screening batch",
)
async def create_batch(payload: BatchCreate, session: DbSession) -> BatchRead:
    await get_job_role_or_404(session, payload.job_role_id)
    if payload.job_description_id is not None:
        await get_job_description_or_404(session, payload.job_description_id)

    batch = ScreeningBatch(
        job_role_id=payload.job_role_id,
        job_description_id=payload.job_description_id,
        name=payload.name,
        recruiter_email=payload.recruiter_email,
        notes=payload.notes,
        status=BatchStatus.CREATED,
    )
    session.add(batch)
    await session.flush()
    return BatchRead.model_validate(batch)


@router.get("", response_model=Page[BatchRead], summary="List screening batches")
async def list_batches(
    session: DbSession,
    pagination: PaginationDep,
    job_role_id: uuid.UUID | None = Query(default=None),
    batch_status: BatchStatus | None = Query(default=None, alias="status"),
) -> Page[BatchRead]:
    filters = []
    if job_role_id:
        filters.append(ScreeningBatch.job_role_id == job_role_id)
    if batch_status:
        filters.append(ScreeningBatch.status == batch_status)

    total = await session.scalar(
        select(func.count()).select_from(ScreeningBatch).where(*filters)
    )

    stmt = (
        select(ScreeningBatch)
        .where(*filters)
        .order_by(ScreeningBatch.created_at.desc())
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    batches = (await session.execute(stmt)).scalars().all()

    return Page[BatchRead](
        items=[BatchRead.model_validate(batch) for batch in batches],
        meta=PageMeta(
            total=total or 0,
            limit=pagination.limit,
            offset=pagination.offset,
            has_more=pagination.offset + len(batches) < (total or 0),
        ),
    )


@router.get("/{batch_id}", response_model=BatchDetail, summary="Get a batch with resumes")
async def get_batch(batch_id: uuid.UUID, session: DbSession) -> BatchDetail:
    batch = await get_batch_or_404(session, batch_id, with_resumes=True)

    detail = BatchDetail.model_validate(batch)
    detail.job_role = JobRoleSummary.model_validate(batch.job_role)
    detail.resumes = [
        ResumeDetail.model_validate(resume)
        for resume in sorted(batch.resumes, key=lambda item: item.created_at)
    ]
    return detail


@router.post(
    "/{batch_id}/resumes",
    response_model=BulkUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bulk-upload resumes into a batch",
)
async def bulk_upload_resumes(
    batch_id: uuid.UUID,
    session: DbSession,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(..., description="One or more resume files"),
) -> BulkUploadResponse:
    """Each file is validated independently — bad files are reported, not fatal."""
    batch = await get_batch_or_404(session, batch_id)

    if not files:
        raise ValidationError("No files were provided.")

    if len(files) > settings.MAX_BULK_UPLOAD_FILES:
        raise ValidationError(
            f"Too many files in one request (max {settings.MAX_BULK_UPLOAD_FILES}).",
            details={"received": len(files), "max": settings.MAX_BULK_UPLOAD_FILES},
        )

    items = await resume_service.ingest_bulk(session, files=files, batch=batch)

    if settings.PARSE_ON_UPLOAD and settings.GROQ_API_KEY:
        for item in items:
            if item.status == "uploaded" and item.resume_id is not None:
                background_tasks.add_task(parse_resume, item.resume_id)

    return BulkUploadResponse(
        batch_id=batch.id,
        received=len(items),
        uploaded=sum(1 for item in items if item.status == "uploaded"),
        duplicates=sum(1 for item in items if item.status == "duplicate"),
        rejected=sum(1 for item in items if item.status == "rejected"),
        items=items,
    )


@router.delete(
    "/{batch_id}",
    response_model=MessageResponse,
    summary="Delete a batch and all its resumes",
)
async def delete_batch(batch_id: uuid.UUID, session: DbSession) -> MessageResponse:
    batch = await get_batch_or_404(session, batch_id, with_resumes=True)

    # Remove blobs first; the cascade takes care of the rows.
    from app.services.storage import resume_storage

    for resume in batch.resumes:
        resume_storage.delete(resume.storage_path)

    await session.delete(batch)
    return MessageResponse(message="Batch and its resumes deleted.")
