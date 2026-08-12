"""Structured shape of an LLM-parsed job description.

Same role as `parsed_resume.py`: doubles as the JSON schema for Groq's tool
calling and as the validator for what comes back.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ParsedJobDescriptionData(BaseModel):
    title: str | None = None
    company: str | None = None
    location: str | None = None
    summary: str | None = Field(default=None, description="1-3 sentence summary of the role")

    # Typed as `| None` (not just a list default) so the JSON schema handed to
    # Groq allows null — the model sometimes emits null instead of [] for an
    # empty list, and Groq's own tool-call validation rejects that against a
    # plain "array" schema with a 400 before we ever see the response. The
    # validator below normalises it back to [] for everything downstream.
    required_skills: list[str] | None = Field(
        default=None,
        description="Skills explicitly required or described as must-have, normalised to common names",
    )
    preferred_skills: list[str] | None = Field(
        default=None,
        description="Skills described as preferred, nice-to-have, or a plus",
    )
    responsibilities: list[str] | None = Field(default=None)
    education: list[str] | None = Field(
        default=None, description="Education requirements, e.g. 'Bachelor's in Computer Science'"
    )

    min_experience_years: float | None = None
    max_experience_years: float | None = None

    @field_validator(
        "required_skills", "preferred_skills", "responsibilities", "education", mode="before"
    )
    @classmethod
    def _null_list_becomes_empty(cls, value: object) -> object:
        return [] if value is None else value


JOB_DESCRIPTION_TOOL_NAME = "extract_job_description"
JOB_DESCRIPTION_TOOL_DESCRIPTION = (
    "Extract structured job requirements from job description text. "
    "Use null or an empty list for anything that cannot be determined — never guess."
)
