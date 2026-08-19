"""Resume request/response models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import AnalysisStatus, ParseStatus, UploadSource
from app.schemas.resume_score import ResumeScoreRead


class ResumeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_role_id: uuid.UUID | None
    batch_id: uuid.UUID | None
    candidate_id: uuid.UUID | None
    job_description_id: uuid.UUID | None
    upload_source: UploadSource

    original_filename: str
    file_extension: str
    content_type: str
    file_size_bytes: int
    content_hash: str

    parse_status: ParseStatus
    parse_error: str | None
    analysis_status: AnalysisStatus
    analysis_error: str | None
    word_count: int | None
    page_count: int | None

    created_at: datetime
    updated_at: datetime


class ResumeDetail(ResumeRead):
    """Full record, including extracted text/data and the score once ready."""

    raw_text: str | None
    parsed_data: dict[str, Any]
    score: ResumeScoreRead | None = None


class ResumeUploadResponse(BaseModel):
    """Result of a single-file candidate upload."""

    resume: ResumeRead
    duplicate: bool = False
    message: str


class BulkUploadItem(BaseModel):
    """Per-file outcome inside a recruiter bulk upload.

    A rejected file never aborts the rest of the batch — the recruiter gets a
    row-level report instead of an all-or-nothing error.
    """

    filename: str
    status: str  # "uploaded" | "duplicate" | "rejected"
    resume_id: uuid.UUID | None = None
    error_code: str | None = None
    error: str | None = None


class BulkUploadResponse(BaseModel):
    batch_id: uuid.UUID
    received: int
    uploaded: int
    duplicates: int
    rejected: int
    items: list[BulkUploadItem]
