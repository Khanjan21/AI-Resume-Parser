"""Job-description request/response models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import ParseStatus


class JobDescriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_role_id: uuid.UUID | None
    title: str
    company: str | None
    location: str | None
    source_filename: str | None
    parse_status: ParseStatus
    parse_error: str | None
    parsed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class JobDescriptionDetail(JobDescriptionRead):
    raw_text: str
    parsed_data: dict[str, Any]
