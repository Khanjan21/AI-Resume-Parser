"""Resume ingestion: validate -> de-duplicate -> persist bytes -> record row."""

from __future__ import annotations

import uuid

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.models.enums import BatchStatus, UploadSource
from app.models.resume import Resume
from app.models.screening_batch import ScreeningBatch
from app.schemas.resume import BulkUploadItem
from app.services.file_validation import validate_upload
from app.services.storage import compute_content_hash, resume_storage

logger = get_logger(__name__)


async def find_duplicate(
    session: AsyncSession,
    *,
    content_hash: str,
    job_role_id: uuid.UUID | None,
    batch_id: uuid.UUID | None,
    job_description_id: uuid.UUID | None = None,
) -> Resume | None:
    """Look for an identical file already ingested in the same scope.

    Scope is the batch for recruiter uploads (a batch's JD, if any, is fixed
    for every resume in it, so it adds nothing to the scope). For candidate
    uploads, scope is the job role *and* the optional JD — the same CV
    against a different role, or the same role but a different specific JD,
    is a legitimate new upload, not a duplicate of the first.
    """
    stmt = select(Resume).where(Resume.content_hash == content_hash)
    if batch_id is not None:
        stmt = stmt.where(Resume.batch_id == batch_id)
    else:
        stmt = stmt.where(
            Resume.batch_id.is_(None),
            Resume.job_role_id == job_role_id,
            Resume.job_description_id == job_description_id,
        )
    return (await session.execute(stmt.limit(1))).scalar_one_or_none()


async def ingest_resume(
    session: AsyncSession,
    *,
    file: UploadFile,
    job_role_id: uuid.UUID | None,
    upload_source: UploadSource,
    batch_id: uuid.UUID | None = None,
    job_description_id: uuid.UUID | None = None,
) -> tuple[Resume, bool]:
    """Ingest one file. Returns (resume, was_duplicate).

    On a duplicate the existing row is returned untouched and no second copy of
    the bytes is written.
    """
    validated = await validate_upload(file)
    content_hash = compute_content_hash(validated.content)

    existing = await find_duplicate(
        session,
        content_hash=content_hash,
        job_role_id=job_role_id,
        batch_id=batch_id,
        job_description_id=job_description_id,
    )
    if existing is not None:
        logger.info("Duplicate upload ignored: %s", validated.original_filename)
        return existing, True

    stored_filename, relative_path = await resume_storage.save(
        validated.content, validated.extension
    )

    resume = Resume(
        job_role_id=job_role_id,
        batch_id=batch_id,
        job_description_id=job_description_id,
        upload_source=upload_source,
        original_filename=validated.original_filename,
        stored_filename=stored_filename,
        storage_path=relative_path,
        file_extension=validated.extension,
        content_type=validated.content_type,
        file_size_bytes=validated.size_bytes,
        content_hash=content_hash,
    )
    session.add(resume)
    await session.flush()
    return resume, False


async def ingest_bulk(
    session: AsyncSession,
    *,
    files: list[UploadFile],
    batch: ScreeningBatch,
) -> list[BulkUploadItem]:
    """Ingest many files into a batch, reporting each file independently."""
    results: list[BulkUploadItem] = []

    for file in files:
        filename = file.filename or "unnamed"
        try:
            resume, duplicate = await ingest_resume(
                session,
                file=file,
                job_role_id=batch.job_role_id,
                upload_source=UploadSource.RECRUITER,
                batch_id=batch.id,
                job_description_id=batch.job_description_id,
            )
            results.append(
                BulkUploadItem(
                    filename=filename,
                    status="duplicate" if duplicate else "uploaded",
                    resume_id=resume.id,
                )
            )
        except AppError as exc:
            results.append(
                BulkUploadItem(
                    filename=filename,
                    status="rejected",
                    error_code=exc.code,
                    error=exc.message,
                )
            )
        except Exception:  # noqa: BLE001 - one bad file must not kill the batch
            logger.exception("Unexpected failure ingesting %s", filename)
            results.append(
                BulkUploadItem(
                    filename=filename,
                    status="rejected",
                    error_code="internal_error",
                    error="File could not be processed.",
                )
            )
        finally:
            await file.close()

    uploaded = sum(1 for item in results if item.status == "uploaded")
    if uploaded:
        batch.total_resumes += uploaded
        batch.status = BatchStatus.UPLOADING

    return results


async def delete_resume(session: AsyncSession, resume: Resume) -> None:
    """Remove the DB row and its stored file.

    The file is deleted after the row so a failure leaves an orphaned blob
    rather than a row pointing at missing bytes.
    """
    storage_path = resume.storage_path
    batch = resume.batch
    await session.delete(resume)
    await session.flush()

    if batch is not None and batch.total_resumes > 0:
        batch.total_resumes -= 1

    if not resume_storage.delete(storage_path):
        logger.warning("Stored file already missing for deleted resume: %s", storage_path)
