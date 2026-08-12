"""Per-resume scoring against a role (and optionally a specific JD).

One row per resume, created the first time it's scored and overwritten on
every re-score — mirroring how `Resume.parsed_data` works for parsing. Day 3
populates the ATS/skill/experience columns plus a weighted `final_score`
(today's components only — `semantic` isn't computed until Day 4, so its
share of a role's configured weights is dropped and the rest renormalised).
`semantic_score` stays null until Day 4 folds it into `final_score` properly,
and `category` (the recruiter-facing shortlist bucket) stays null until Day 5
— both already exist as columns so neither day needs another migration.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.resume import Resume


class ResumeScore(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "resume_scores"

    resume_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("resumes.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    # Denormalised copies of what the resume was scored against, so Day 5's
    # ranking queries don't have to join through resumes -> batches every time.
    job_role_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("job_roles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_description_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("job_descriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # --- Day 3: ATS keyword coverage ---
    ats_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    matched_ats_keywords: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    # --- Day 3: required-skill coverage ---
    required_skill_match: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    matched_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    missing_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    # --- Day 3: experience fit ---
    experience_match: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    candidate_experience_years: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Day 3: rule-based improvement suggestions ---
    suggestions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    # --- Day 3: weighted blend of ats/required_skills/experience (renormalised
    # to exclude `semantic`, which isn't computed until Day 4 recomputes this) ---
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Day 4: semantic similarity (null until then) ---
    semantic_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Day 5: recruiter-facing shortlist bucket (null until then) ---
    category: Mapped[str | None] = mapped_column(String(20), nullable=True)

    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    resume: Mapped["Resume"] = relationship(back_populates="score")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<ResumeScore resume_id={self.resume_id} ats={self.ats_score:.0f}>"
