"""Uploaded resume files and their extraction state."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AnalysisStatus, ParseStatus, UploadSource

if TYPE_CHECKING:
    from app.models.candidate import Candidate
    from app.models.job_role import JobRole
    from app.models.screening_batch import ScreeningBatch


class Resume(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One uploaded file.

    The row is created the moment bytes land on disk; `raw_text`, `parsed_data`
    and the candidate link are filled in by the Day 2 parsing pipeline.
    """

    __tablename__ = "resumes"
    __table_args__ = (
        # Guards against the same file being uploaded twice into one batch.
        # NULL batch_id rows (candidate flow) are exempt: Postgres treats NULLs
        # as distinct in unique constraints.
        UniqueConstraint("batch_id", "content_hash", name="uq_resume_batch_content"),
        Index("ix_resumes_role_status", "job_role_id", "parse_status"),
    )

    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_role_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("job_roles.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("screening_batches.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    upload_source: Mapped[UploadSource] = mapped_column(
        String(20), nullable=False, default=UploadSource.CANDIDATE, index=True
    )

    # --- File metadata ---
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(600), nullable=False)
    file_extension: Mapped[str] = mapped_column(String(16), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # --- Extraction (Day 2) ---
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parsed_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    parse_status: Mapped[ParseStatus] = mapped_column(
        String(20), nullable=False, default=ParseStatus.PENDING, index=True
    )
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Scoring (Days 3-5) ---
    analysis_status: Mapped[AnalysisStatus] = mapped_column(
        String(20), nullable=False, default=AnalysisStatus.PENDING, index=True
    )

    candidate: Mapped["Candidate | None"] = relationship(back_populates="resumes")
    job_role: Mapped["JobRole | None"] = relationship(back_populates="resumes")
    batch: Mapped["ScreeningBatch | None"] = relationship(back_populates="resumes")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Resume {self.original_filename} ({self.parse_status})>"
