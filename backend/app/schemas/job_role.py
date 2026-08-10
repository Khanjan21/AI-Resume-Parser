"""Job-role request/response models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ExperienceLevel


class JobRoleSummary(BaseModel):
    """Compact shape for the role picker on both flows."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    title: str
    category: str
    summary: str
    default_level: ExperienceLevel
    min_experience_years: float
    max_experience_years: float | None
    required_skills: list[str]
    is_active: bool


class JobRoleDetail(JobRoleSummary):
    """Everything the scoring pipeline needs about a role."""

    description: str
    preferred_skills: list[str]
    nice_to_have_skills: list[str]
    responsibilities: list[str]
    education: list[str]
    ats_keywords: list[str]
    scoring_weights: dict[str, Any]
    is_system: bool
    created_at: datetime
    updated_at: datetime


class JobRoleCreate(BaseModel):
    """Recruiter-defined role (custom positions beyond the shipped catalogue)."""

    title: str = Field(..., min_length=2, max_length=160)
    category: str = Field(default="engineering", max_length=80)
    summary: str = Field(default="", max_length=500)
    description: str = ""
    default_level: ExperienceLevel = ExperienceLevel.MID
    min_experience_years: float = Field(default=0.0, ge=0, le=50)
    max_experience_years: float | None = Field(default=None, ge=0, le=60)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    ats_keywords: list[str] = Field(default_factory=list)
    scoring_weights: dict[str, float] = Field(default_factory=dict)
