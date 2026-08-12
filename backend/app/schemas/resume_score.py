"""Resume-score response model.

Day 3 populates everything except `semantic_score` (Day 4) and `final_score` /
`category` (Day 5), which stay null until those land.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ResumeScoreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    resume_id: uuid.UUID
    job_role_id: uuid.UUID | None
    job_description_id: uuid.UUID | None

    ats_score: float
    matched_ats_keywords: list[str]

    required_skill_match: float
    matched_skills: list[str]
    missing_skills: list[str]

    experience_match: float
    candidate_experience_years: float | None

    suggestions: list[str]

    semantic_score: float | None
    final_score: float | None
    category: str | None

    scored_at: datetime
