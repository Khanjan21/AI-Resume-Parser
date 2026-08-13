"""Unit tests for the embedding-text builders — pure string assembly, no model."""

from __future__ import annotations

from app.services.embedding_text import (
    build_job_description_embedding_text,
    build_job_role_embedding_text,
    build_resume_embedding_text,
)


class TestJobRoleEmbeddingText:
    def test_includes_all_provided_fields(self) -> None:
        text = build_job_role_embedding_text(
            title="AI Engineer",
            summary="Builds LLM apps.",
            description="Longer description.",
            required_skills=["Python", "RAG"],
            preferred_skills=["Docker"],
            responsibilities=["Ship features"],
        )
        assert "AI Engineer" in text
        assert "Builds LLM apps." in text
        assert "Python, RAG" in text
        assert "Docker" in text
        assert "Ship features" in text

    def test_omits_empty_skill_lists_cleanly(self) -> None:
        text = build_job_role_embedding_text(
            title="Role",
            summary="",
            description="",
            required_skills=[],
            preferred_skills=[],
            responsibilities=[],
        )
        assert text == "Role"


class TestJobDescriptionEmbeddingText:
    def test_uses_parsed_data_when_available(self) -> None:
        text = build_job_description_embedding_text(
            title="AI Engineer",
            parsed_data={
                "summary": "Great role.",
                "required_skills": ["Python"],
                "preferred_skills": ["AWS"],
                "responsibilities": ["Build things"],
            },
            raw_text="raw fallback text",
        )
        assert "Great role." in text
        assert "Python" in text
        assert "raw fallback text" not in text

    def test_falls_back_to_raw_text_when_unparsed(self) -> None:
        text = build_job_description_embedding_text(
            title="", parsed_data={}, raw_text="Only raw text available."
        )
        assert text == "Only raw text available."


class TestResumeEmbeddingText:
    def test_includes_summary_skills_experience_education(self) -> None:
        text = build_resume_embedding_text(
            {
                "current_title": "AI Engineer",
                "summary": "4 years building LLM apps.",
                "skills": ["Python", "RAG"],
                "experience": [
                    {"title": "Engineer", "company": "Acme", "description": "Built things."}
                ],
                "education": [{"degree": "BSc", "institution": "MIT"}],
            }
        )
        assert "AI Engineer" in text
        assert "4 years building LLM apps." in text
        assert "Python, RAG" in text
        assert "Engineer at Acme: Built things." in text
        assert "BSc, MIT" in text

    def test_handles_completely_empty_parsed_data(self) -> None:
        assert build_resume_embedding_text({}) == ""

    def test_handles_missing_optional_experience_fields(self) -> None:
        text = build_resume_embedding_text({"experience": [{"title": "Engineer"}]})
        assert "Engineer at" in text
