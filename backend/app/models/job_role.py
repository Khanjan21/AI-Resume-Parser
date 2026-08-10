"""Job roles — the catalogue candidates and recruiters screen against."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Float, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ExperienceLevel

if TYPE_CHECKING:
    from app.models.job_description import JobDescription
    from app.models.resume import Resume
    from app.models.screening_batch import ScreeningBatch


class JobRole(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A screenable position (AI Engineer, Data Scientist, ...).

    Skill lists are JSONB rather than a join table on purpose: they are read as a
    whole document by the matcher (Day 4) and are never queried field-by-field.
    """

    __tablename__ = "job_roles"
    __table_args__ = (Index("ix_job_roles_active_title", "is_active", "title"),)

    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False, default="engineering")
    summary: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    default_level: Mapped[ExperienceLevel] = mapped_column(
        String(20), nullable=False, default=ExperienceLevel.MID
    )
    min_experience_years: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_experience_years: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Matching vocabulary (consumed from Day 3 onward) ---
    required_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    preferred_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    nice_to_have_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    responsibilities: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    education: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    ats_keywords: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    # --- Scoring configuration ---
    # e.g. {"ats": 0.20, "required_skills": 0.35, "semantic": 0.25, "experience": 0.20}
    scoring_weights: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # System roles ship with the product and are refreshed by the seeder.
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    resumes: Mapped[list["Resume"]] = relationship(
        back_populates="job_role", cascade="all, delete-orphan"
    )
    batches: Mapped[list["ScreeningBatch"]] = relationship(
        back_populates="job_role", cascade="all, delete-orphan"
    )
    job_descriptions: Mapped[list["JobDescription"]] = relationship(
        back_populates="job_role"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<JobRole {self.slug}>"
