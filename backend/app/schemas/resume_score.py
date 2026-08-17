"""Resume-score response model — null until a resume has been scored at all
(`Resume.score` is `None`), populated in full on every successful pass:
`ats_score`/`required_skill_match`/`experience_match` (Day 3), `semantic_score`
(Day 4), `final_score`/`category` (Day 5).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ShortlistCategory


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
    category: ShortlistCategory | None

    scored_at: datetime
