"""Screening-batch request/response models."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import BatchStatus
from app.schemas.job_role import JobRoleSummary
from app.schemas.resume import ResumeDetail


class BatchCreate(BaseModel):
    job_role_id: uuid.UUID
    job_description_id: uuid.UUID | None = Field(
        default=None,
        description="Optional specific JD to screen against, in addition to the role's generic vocabulary",
    )
    name: str = Field(..., min_length=1, max_length=200)
    recruiter_email: EmailStr | None = None
    notes: str | None = Field(default=None, max_length=2000)


class BatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_role_id: uuid.UUID
    job_description_id: uuid.UUID | None
    name: str
    recruiter_email: str | None
    notes: str | None
    status: BatchStatus
    total_resumes: int
    parsed_resumes: int
    failed_resumes: int
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BatchCategoryCounts(BaseModel):
    """How a batch's resumes split across Day 5's shortlist buckets.

    `unscored` covers resumes still parsing/scoring, or that failed either
    step — the three category counts plus `unscored` always add up to the
    batch's total resume count.
    """

    strong_match: int = 0
    consider: int = 0
    weak_match: int = 0
    unscored: int = 0


class BatchDetail(BatchRead):
    job_role: JobRoleSummary | None = None
    resumes: list[ResumeDetail] = []
    category_counts: BatchCategoryCounts = Field(default_factory=BatchCategoryCounts)
