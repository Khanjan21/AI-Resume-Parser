"""Builds the plain-text representation of each entity that gets embedded.

Deliberately NOT the raw resume file text — that's full of contact details,
formatting artefacts and page-layout noise that dilutes the signal. Each
builder assembles a clean, information-dense paragraph from already-parsed
structured data instead, which is what empirically produced clean similarity
separation during calibration (see the Day 4 section in the README).
"""

from __future__ import annotations

from typing import Any


def _join_nonempty(parts: list[str | None]) -> str:
    return "\n".join(p.strip() for p in parts if p and p.strip())


def build_job_role_embedding_text(
    *,
    title: str,
    summary: str,
    description: str,
    required_skills: list[str],
    preferred_skills: list[str],
    responsibilities: list[str],
) -> str:
    return _join_nonempty(
        [
            title,
            summary,
            description,
            "Required skills: " + ", ".join(required_skills) if required_skills else None,
            "Preferred skills: " + ", ".join(preferred_skills) if preferred_skills else None,
            "Responsibilities: " + "; ".join(responsibilities) if responsibilities else None,
        ]
    )


def build_job_description_embedding_text(
    *, title: str, parsed_data: dict[str, Any], raw_text: str
) -> str:
    required = parsed_data.get("required_skills") or []
    preferred = parsed_data.get("preferred_skills") or []
    responsibilities = parsed_data.get("responsibilities") or []
    summary = parsed_data.get("summary")

    text = _join_nonempty(
        [
            title,
            summary,
            "Required skills: " + ", ".join(required) if required else None,
            "Preferred skills: " + ", ".join(preferred) if preferred else None,
            "Responsibilities: " + "; ".join(responsibilities) if responsibilities else None,
        ]
    )
    # A JD that failed to parse still has raw_text — better than nothing.
    return text or raw_text


def build_resume_embedding_text(parsed_data: dict[str, Any]) -> str:
    summary = parsed_data.get("summary")
    current_title = parsed_data.get("current_title")
    skills = parsed_data.get("skills") or []

    experience_lines = [
        f"{entry.get('title', '')} at {entry.get('company', '')}: {entry.get('description') or ''}".strip()
        for entry in (parsed_data.get("experience") or [])
    ]
    education_lines = [
        f"{entry.get('degree', '')}, {entry.get('institution', '')}".strip(", ")
        for entry in (parsed_data.get("education") or [])
    ]

    return _join_nonempty(
        [
            current_title,
            summary,
            "Skills: " + ", ".join(skills) if skills else None,
            "Experience: " + "; ".join(experience_lines) if experience_lines else None,
            "Education: " + "; ".join(education_lines) if education_lines else None,
        ]
    )
