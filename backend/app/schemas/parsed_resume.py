"""Structured shape of an LLM-parsed resume.

These models serve two purposes: `model_json_schema()` becomes the tool
definition handed to Groq (forcing its output into this exact shape), and
the same class validates what comes back before it's persisted to
`Resume.parsed_data`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExperienceEntry(BaseModel):
    title: str
    company: str
    start_date: str | None = Field(
        default=None, description="Free-form, e.g. 'Jan 2021' or '2021'"
    )
    end_date: str | None = Field(
        default=None, description="Null if this is the current role"
    )
    is_current: bool = False
    description: str | None = Field(
        default=None, description="Bullet points or summary of this role, as one string"
    )


class EducationEntry(BaseModel):
    degree: str
    institution: str
    start_year: int | None = None
    end_year: int | None = None


class ParsedResumeData(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None

    summary: str | None = Field(
        default=None, description="Professional summary, 1-3 sentences"
    )
    current_title: str | None = None
    total_experience_years: float | None = Field(
        default=None, description="Total professional experience in years, estimated from the work history"
    )

    skills: list[str] = Field(
        default_factory=list,
        description="Flat list of technical and professional skills, normalised to common names (e.g. 'PyTorch' not 'pytorch')",
    )
    experience: list[ExperienceEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)


RESUME_TOOL_NAME = "extract_resume"
RESUME_TOOL_DESCRIPTION = (
    "Extract structured candidate data from resume text. "
    "Use null for any field that cannot be determined from the text — never guess."
)
