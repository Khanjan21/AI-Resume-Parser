"""Recruiter-supplied job descriptions (free text, parsed on Day 2)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ParseStatus

if TYPE_CHECKING:
    from app.models.job_role import JobRole
    from app.models.screening_batch import ScreeningBatch


class JobDescription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A concrete JD, optionally anchored to one of the catalogue roles.

    A batch may screen against the generic role only, or against a specific JD
    that overrides / extends the role's skill vocabulary.
    """

    __tablename__ = "job_descriptions"

    job_role_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("job_roles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    location: Mapped[str | None] = mapped_column(String(160), nullable=True)

    raw_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Structured extraction result — filled by the Day 2 LLM parser.
    parsed_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    parse_status: Mapped[ParseStatus] = mapped_column(
        String(20), nullable=False, default=ParseStatus.PENDING, index=True
    )
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job_role: Mapped["JobRole | None"] = relationship(back_populates="job_descriptions")
    batches: Mapped[list["ScreeningBatch"]] = relationship(
        back_populates="job_description"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<JobDescription {self.title}>"
