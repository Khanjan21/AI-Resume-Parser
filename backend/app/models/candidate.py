"""Candidate identity extracted from (or supplied alongside) a resume."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.resume import Resume


class Candidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A person. Fields beyond name/email are populated by parsing on Day 2.

    Email is intentionally *not* unique: the same address can legitimately appear
    across separate recruiter batches, and de-duplication is a scoring-time
    concern rather than a storage constraint.
    """

    __tablename__ = "candidates"

    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    location: Mapped[str | None] = mapped_column(String(160), nullable=True)

    linkedin_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    github_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    portfolio_url: Mapped[str | None] = mapped_column(String(400), nullable=True)

    total_experience_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_title: Mapped[str | None] = mapped_column(String(200), nullable=True)

    resumes: Mapped[list["Resume"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Candidate {self.full_name or self.email or self.id}>"
