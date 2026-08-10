"""Enumerations shared across models and schemas."""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """String-valued enum that serialises cleanly through Pydantic and JSON."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class UploadSource(StrEnum):
    """Which flow produced the resume."""

    CANDIDATE = "candidate"
    RECRUITER = "recruiter"


class ParseStatus(StrEnum):
    """Lifecycle of resume text extraction (Day 2 does the work)."""

    PENDING = "pending"
    PROCESSING = "processing"
    PARSED = "parsed"
    FAILED = "failed"


class AnalysisStatus(StrEnum):
    """Lifecycle of scoring (Days 3-5)."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class BatchStatus(StrEnum):
    """Lifecycle of a recruiter bulk-screening batch."""

    CREATED = "created"
    UPLOADING = "uploading"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ExperienceLevel(StrEnum):
    ENTRY = "entry"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"


class SkillImportance(StrEnum):
    """Weighting bucket for a skill within a job role."""

    REQUIRED = "required"
    PREFERRED = "preferred"
    NICE_TO_HAVE = "nice_to_have"
