"""Structured shape of an LLM-parsed resume.

These models serve two purposes: `model_json_schema()` becomes the tool
definition handed to Groq (forcing its output into this exact shape), and
the same class validates what comes back before it's persisted to
`Resume.parsed_data`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


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

    # Typed as `| None` (not just a list default) so the JSON schema handed to
    # Groq allows null — the model sometimes emits null instead of [] for an
    # empty list, and Groq's own tool-call validation rejects that against a
    # plain "array" schema with a 400 before we ever see the response. The
    # validator below normalises it back to [] for everything downstream.
    skills: list[str] | None = Field(
        default=None,
        description="Flat list of technical and professional skills, normalised to common names (e.g. 'PyTorch' not 'pytorch')",
    )
    experience: list[ExperienceEntry] | None = Field(default=None)
    education: list[EducationEntry] | None = Field(default=None)
    certifications: list[str] | None = Field(default=None)

    @field_validator("skills", "experience", "education", "certifications", mode="before")
    @classmethod
    def _null_list_becomes_empty(cls, value: object) -> object:
        return [] if value is None else value


RESUME_TOOL_NAME = "extract_resume"
RESUME_TOOL_DESCRIPTION = (
    "Extract structured candidate data from resume text. "
    "Use null for any field that cannot be determined from the text — never guess."
)
