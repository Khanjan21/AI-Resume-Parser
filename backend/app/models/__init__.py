"""Model package — importing it registers every table on `Base.metadata`.

Alembic autogenerate relies on this, so new models must be re-exported here.
"""

from app.db.base import Base
from app.models.candidate import Candidate
from app.models.enums import (
    AnalysisStatus,
    BatchStatus,
    ExperienceLevel,
    ParseStatus,
    SkillImportance,
    UploadSource,
)
from app.models.job_description import JobDescription
from app.models.job_role import JobRole
from app.models.resume import Resume
from app.models.screening_batch import ScreeningBatch

__all__ = [
    "AnalysisStatus",
    "Base",
    "BatchStatus",
    "Candidate",
    "ExperienceLevel",
    "JobDescription",
    "JobRole",
    "ParseStatus",
    "Resume",
    "ScreeningBatch",
    "SkillImportance",
    "UploadSource",
]
