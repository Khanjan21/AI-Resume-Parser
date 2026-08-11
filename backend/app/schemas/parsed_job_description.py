"""Structured shape of an LLM-parsed job description.

Same role as `parsed_resume.py`: doubles as the JSON schema for Groq's tool
calling and as the validator for what comes back.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ParsedJobDescriptionData(BaseModel):
    title: str | None = None
    company: str | None = None
    location: str | None = None
    summary: str | None = Field(default=None, description="1-3 sentence summary of the role")

    required_skills: list[str] = Field(
        default_factory=list,
        description="Skills explicitly required or described as must-have, normalised to common names",
    )
    preferred_skills: list[str] = Field(
        default_factory=list,
        description="Skills described as preferred, nice-to-have, or a plus",
    )
    responsibilities: list[str] = Field(default_factory=list)
    education: list[str] = Field(
        default_factory=list, description="Education requirements, e.g. 'Bachelor's in Computer Science'"
    )

    min_experience_years: float | None = None
    max_experience_years: float | None = None


JOB_DESCRIPTION_TOOL_NAME = "extract_job_description"
JOB_DESCRIPTION_TOOL_DESCRIPTION = (
    "Extract structured job requirements from job description text. "
    "Use null or an empty list for anything that cannot be determined — never guess."
)
