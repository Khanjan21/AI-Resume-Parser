"""A recruiter's bulk-screening run: one job target, many resumes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import BatchStatus

if TYPE_CHECKING:
    from app.models.job_description import JobDescription
    from app.models.job_role import JobRole
    from app.models.resume import Resume


class ScreeningBatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Groups the resumes uploaded together so they can be ranked against
    each other on Day 5."""

    __tablename__ = "screening_batches"

    job_role_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("job_roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_description_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("job_descriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    recruiter_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[BatchStatus] = mapped_column(
        String(20), nullable=False, default=BatchStatus.CREATED, index=True
    )

    # Denormalised counters so the recruiter dashboard never has to aggregate.
    total_resumes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parsed_resumes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_resumes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    job_role: Mapped["JobRole"] = relationship(back_populates="batches")
    job_description: Mapped["JobDescription | None"] = relationship(back_populates="batches")
    resumes: Mapped[list["Resume"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<ScreeningBatch {self.name} ({self.status})>"
