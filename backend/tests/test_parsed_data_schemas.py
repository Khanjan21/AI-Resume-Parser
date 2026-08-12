"""Regression tests for the parsed-data schemas' null-list handling.

Groq occasionally emits `null` rather than `[]` for an empty list field. If a
schema's field type is a plain `list[...]` (no `| None`), the JSON schema we
hand Groq forbids null, and Groq's own tool-call validation rejects the
response with a 400 *before* it ever reaches our validation — a real failure
seen live against a job description ("education: expected array, but got
null"). Every list field must accept null in its schema and normalise it to
`[]` so callers never have to special-case None.
"""

from __future__ import annotations

import pytest

from app.schemas.parsed_job_description import ParsedJobDescriptionData
from app.schemas.parsed_resume import ParsedResumeData

RESUME_LIST_FIELDS = ["skills", "experience", "education", "certifications"]
JD_LIST_FIELDS = ["required_skills", "preferred_skills", "responsibilities", "education"]


class TestSchemaAllowsNull:
    @pytest.mark.parametrize("field_name", RESUME_LIST_FIELDS)
    def test_resume_list_field_schema_permits_null(self, field_name: str) -> None:
        prop = ParsedResumeData.model_json_schema()["properties"][field_name]
        types = {branch.get("type") for branch in prop.get("anyOf", [])}
        assert "null" in types, f"{field_name}'s schema must allow null for Groq to accept it"

    @pytest.mark.parametrize("field_name", JD_LIST_FIELDS)
    def test_job_description_list_field_schema_permits_null(self, field_name: str) -> None:
        prop = ParsedJobDescriptionData.model_json_schema()["properties"][field_name]
        types = {branch.get("type") for branch in prop.get("anyOf", [])}
        assert "null" in types, f"{field_name}'s schema must allow null for Groq to accept it"


class TestNullNormalisesToEmptyList:
    @pytest.mark.parametrize("field_name", RESUME_LIST_FIELDS)
    def test_resume_null_becomes_empty_list(self, field_name: str) -> None:
        parsed = ParsedResumeData.model_validate({field_name: None})
        assert getattr(parsed, field_name) == []

    @pytest.mark.parametrize("field_name", JD_LIST_FIELDS)
    def test_job_description_null_becomes_empty_list(self, field_name: str) -> None:
        parsed = ParsedJobDescriptionData.model_validate({field_name: None})
        assert getattr(parsed, field_name) == []

    def test_resume_still_accepts_a_real_list(self) -> None:
        parsed = ParsedResumeData.model_validate({"skills": ["Python", "SQL"]})
        assert parsed.skills == ["Python", "SQL"]
