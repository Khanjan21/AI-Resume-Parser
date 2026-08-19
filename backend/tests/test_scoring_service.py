"""Unit tests for the ATS scoring service — pure rule-based math, no LLM."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.enums import AnalysisStatus, BatchStatus, ShortlistCategory
from app.models.job_description import JobDescription
from app.models.job_role import JobRole
from app.models.resume import Resume
from app.models.resume_score import ResumeScore
from app.models.screening_batch import ScreeningBatch
from app.services import scoring_service


async def _make_role(
    session,
    *,
    required_skills=None,
    preferred_skills=None,
    ats_keywords=None,
    min_experience_years=0.0,
    max_experience_years=None,
    scoring_weights=None,
) -> JobRole:
    role = JobRole(
        slug=f"role-{uuid.uuid4().hex[:8]}",
        title="Test Role",
        required_skills=required_skills or [],
        preferred_skills=preferred_skills or [],
        nice_to_have_skills=[],
        ats_keywords=ats_keywords or [],
        responsibilities=[],
        education=[],
        min_experience_years=min_experience_years,
        max_experience_years=max_experience_years,
        scoring_weights=scoring_weights or {},
    )
    session.add(role)
    await session.commit()
    return role


async def _make_resume(
    session, *, role: JobRole, raw_text: str, parsed_data: dict, batch_id=None,
    job_description_id=None,
) -> Resume:
    resume = Resume(
        job_role_id=role.id,
        batch_id=batch_id,
        job_description_id=job_description_id,
        upload_source="candidate",
        original_filename="cv.txt",
        stored_filename="x.txt",
        storage_path="2026/01/x.txt",
        file_extension=".txt",
        content_type="text/plain",
        file_size_bytes=len(raw_text),
        content_hash=uuid.uuid4().hex,
        raw_text=raw_text,
        parsed_data=parsed_data,
        parse_status="parsed",
    )
    session.add(resume)
    await session.commit()
    return resume


class TestAtsKeywordScoring:
    async def test_partial_keyword_coverage(self, session, parsing_env) -> None:
        role = await _make_role(
            session, ats_keywords=["python", "docker", "kubernetes", "react"]
        )
        resume = await _make_resume(
            session,
            role=role,
            raw_text="Experienced with Python and Docker in production.",
            parsed_data={},
        )

        await scoring_service.score_resume(resume.id)

        score = (
            await session.execute(
                select(ResumeScore).where(ResumeScore.resume_id == resume.id)
            )
        ).scalar_one()
        assert score.ats_score == 50.0
        assert set(score.matched_ats_keywords) == {"python", "docker"}

    async def test_matching_is_case_insensitive(self, session, parsing_env) -> None:
        role = await _make_role(session, ats_keywords=["RAG", "LangChain"])
        resume = await _make_resume(
            session, role=role, raw_text="Built systems using rag and LANGCHAIN.", parsed_data={}
        )

        await scoring_service.score_resume(resume.id)

        score = (
            await session.execute(
                select(ResumeScore).where(ResumeScore.resume_id == resume.id)
            )
        ).scalar_one()
        assert score.ats_score == 100.0

    async def test_no_keywords_defined_scores_full_marks(
        self, session, parsing_env
    ) -> None:
        role = await _make_role(session, ats_keywords=[])
        resume = await _make_resume(session, role=role, raw_text="anything", parsed_data={})

        await scoring_service.score_resume(resume.id)

        score = (
            await session.execute(
                select(ResumeScore).where(ResumeScore.resume_id == resume.id)
            )
        ).scalar_one()
        assert score.ats_score == 100.0


class TestRequiredSkillMatch:
    async def test_partial_match_reports_missing_skills(
        self, session, parsing_env
    ) -> None:
        role = await _make_role(
            session,
            required_skills=["Python", "SQL", "Docker"],
            preferred_skills=["AWS"],
        )
        resume = await _make_resume(
            session,
            role=role,
            raw_text="resume text",
            parsed_data={"skills": ["python", "Docker", "AWS"]},
        )

        await scoring_service.score_resume(resume.id)

        score = (
            await session.execute(
                select(ResumeScore).where(ResumeScore.resume_id == resume.id)
            )
        ).scalar_one()
        assert score.required_skill_match == pytest.approx(66.7, abs=0.1)
        assert score.missing_skills == ["SQL"]
        assert set(score.matched_skills) == {"Python", "Docker", "AWS"}

    async def test_no_required_skills_scores_full_marks(
        self, session, parsing_env
    ) -> None:
        role = await _make_role(session, required_skills=[])
        resume = await _make_resume(
            session, role=role, raw_text="x", parsed_data={"skills": []}
        )

        await scoring_service.score_resume(resume.id)

        score = (
            await session.execute(
                select(ResumeScore).where(ResumeScore.resume_id == resume.id)
            )
        ).scalar_one()
        assert score.required_skill_match == 100.0
        assert score.missing_skills == []


class TestExperienceMatch:
    @pytest.mark.parametrize(
        ("min_years", "max_years", "candidate_years", "expected"),
        [
            (3.0, 8.0, 5.0, 100.0),
            (3.0, 8.0, 10.0, 100.0),  # overqualified is not penalised
            (3.0, 8.0, None, 50.0),  # unstated is neutral, not zero
            (0.0, 8.0, 0.0, 100.0),  # min=0 (our seeded default) always clears
            (4.0, None, 2.0, 50.0),  # 2/4 * 100
        ],
    )
    async def test_experience_scoring(
        self, session, parsing_env, min_years, max_years, candidate_years, expected
    ) -> None:
        role = await _make_role(
            session, min_experience_years=min_years, max_experience_years=max_years
        )
        resume = await _make_resume(
            session,
            role=role,
            raw_text="x",
            parsed_data={"total_experience_years": candidate_years},
        )

        await scoring_service.score_resume(resume.id)

        score = (
            await session.execute(
                select(ResumeScore).where(ResumeScore.resume_id == resume.id)
            )
        ).scalar_one()
        assert score.experience_match == pytest.approx(expected, abs=0.1)
        assert score.candidate_experience_years == candidate_years


class TestFinalScore:
    async def test_weighted_blend_of_available_components(
        self, session, parsing_env
    ) -> None:
        # ats=100 (no keywords to miss), required_skill_match=0 (nothing
        # matches), experience_match=100 (min=0). Weights renormalise over
        # just ats/required_skills/experience — the 0.3 "semantic" share is
        # dropped and the rest scaled up proportionally.
        role = await _make_role(
            session,
            required_skills=["Python"],
            scoring_weights={"ats": 0.2, "required_skills": 0.3, "semantic": 0.3, "experience": 0.2},
        )
        resume = await _make_resume(
            session, role=role, raw_text="x", parsed_data={"skills": [], "total_experience_years": 5}
        )

        await scoring_service.score_resume(resume.id)

        score = (
            await session.execute(
                select(ResumeScore).where(ResumeScore.resume_id == resume.id)
            )
        ).scalar_one()
        assert score.ats_score == 100.0
        assert score.required_skill_match == 0.0
        assert score.experience_match == 100.0
        # (100*0.2 + 0*0.3 + 100*0.2) / (0.2+0.3+0.2) = 40/0.7 = 57.14...
        assert score.final_score == pytest.approx(57.1, abs=0.1)
        assert score.category == ShortlistCategory.CONSIDER

    async def test_falls_back_to_plain_average_with_no_configured_weights(
        self, session, parsing_env
    ) -> None:
        role = await _make_role(session, required_skills=["Python"], scoring_weights={})
        resume = await _make_resume(
            session, role=role, raw_text="x", parsed_data={"skills": [], "total_experience_years": 5}
        )

        await scoring_service.score_resume(resume.id)

        score = (
            await session.execute(
                select(ResumeScore).where(ResumeScore.resume_id == resume.id)
            )
        ).scalar_one()
        # ats=100, required_skill_match=0, experience_match=100 -> plain average
        assert score.final_score == pytest.approx(66.7, abs=0.1)
        assert score.category == ShortlistCategory.CONSIDER


class TestCategorize:
    """Pure math, no DB needed."""

    def test_strong_match_at_and_above_threshold(self) -> None:
        assert scoring_service._categorize(75.0) == ShortlistCategory.STRONG_MATCH
        assert scoring_service._categorize(100.0) == ShortlistCategory.STRONG_MATCH

    def test_consider_between_thresholds(self) -> None:
        assert scoring_service._categorize(45.0) == ShortlistCategory.CONSIDER
        assert scoring_service._categorize(74.9) == ShortlistCategory.CONSIDER

    def test_weak_match_below_consider_threshold(self) -> None:
        assert scoring_service._categorize(44.9) == ShortlistCategory.WEAK_MATCH
        assert scoring_service._categorize(0.0) == ShortlistCategory.WEAK_MATCH

    def test_none_final_score_stays_uncategorized(self) -> None:
        assert scoring_service._categorize(None) is None


class TestScoreOverallWithSemantic:
    """Pure math, no DB needed — exercises the weighting logic directly."""

    def test_includes_semantic_when_present(self) -> None:
        result = scoring_service._score_overall(
            ats_score=100.0,
            required_skill_match=0.0,
            experience_match=100.0,
            semantic_score=50.0,
            weights={"ats": 0.2, "required_skills": 0.3, "semantic": 0.3, "experience": 0.2},
        )
        # (100*.2 + 0*.3 + 50*.3 + 100*.2) / 1.0 = 55.0
        assert result == 55.0

    def test_drops_semantic_share_when_none(self) -> None:
        result = scoring_service._score_overall(
            ats_score=100.0,
            required_skill_match=0.0,
            experience_match=100.0,
            semantic_score=None,
            weights={"ats": 0.2, "required_skills": 0.3, "semantic": 0.3, "experience": 0.2},
        )
        # renormalised over ats+required+experience (0.7 total weight)
        assert result == pytest.approx(57.1, abs=0.1)


class TestScoreSemanticMath:
    """Pure math, no DB needed."""

    def test_identical_vectors_score_100(self) -> None:
        vector = [1.0, 0.0, 0.0]
        assert scoring_service._score_semantic(vector, vector) == 100.0

    def test_orthogonal_vectors_clamp_to_zero(self) -> None:
        # similarity=0.0, below the 0.35 floor -> clamps rather than going negative
        assert scoring_service._score_semantic([1.0, 0.0], [0.0, 1.0]) == 0.0

    def test_similarity_at_ceiling_scores_100(self) -> None:
        # Two unit vectors 90% aligned by construction (dot product = 0.9).
        a = [1.0, 0.0]
        b = [0.9, (1 - 0.9**2) ** 0.5]
        assert scoring_service._score_semantic(a, b) == 100.0


class TestAverageVector:
    def test_averages_elementwise(self) -> None:
        assert scoring_service._average_vector([[1.0, 2.0], [3.0, 4.0]]) == [2.0, 3.0]

    def test_single_vector_is_unchanged(self) -> None:
        assert scoring_service._average_vector([[1.0, 2.0]]) == [1.0, 2.0]


class TestSemanticScoreIntegration:
    async def test_computes_and_persists_a_semantic_score(
        self, session, parsing_env, fake_embeddings
    ) -> None:
        role = await _make_role(
            session,
            required_skills=["Python"],
            scoring_weights={"ats": 0.2, "required_skills": 0.3, "semantic": 0.3, "experience": 0.2},
        )
        resume = await _make_resume(
            session,
            role=role,
            raw_text="x",
            parsed_data={"skills": ["Python"], "summary": "An experienced engineer."},
        )

        await scoring_service.score_resume(resume.id)
        await session.refresh(resume)
        await session.refresh(role)

        score = (
            await session.execute(
                select(ResumeScore).where(ResumeScore.resume_id == resume.id)
            )
        ).scalar_one()
        assert score.semantic_score is not None
        assert 0.0 <= score.semantic_score <= 100.0
        assert resume.embedding is not None
        assert role.embedding is not None  # backfilled since this role had none

    async def test_semantic_score_is_none_without_a_role(
        self, session, parsing_env
    ) -> None:
        resume = Resume(
            job_role_id=None,
            upload_source="candidate",
            original_filename="cv.txt",
            stored_filename="x.txt",
            storage_path="2026/01/x.txt",
            file_extension=".txt",
            content_type="text/plain",
            file_size_bytes=1,
            content_hash=str(uuid.uuid4()),
            raw_text="x",
            parsed_data={"skills": ["Python"], "summary": "A profile."},
            parse_status="parsed",
        )
        session.add(resume)
        await session.commit()

        await scoring_service.score_resume(resume.id)

        score = (
            await session.execute(
                select(ResumeScore).where(ResumeScore.resume_id == resume.id)
            )
        ).scalar_one()
        assert score.semantic_score is None

    async def test_identical_profile_and_role_text_scores_perfectly(
        self, session, parsing_env, fake_embeddings
    ) -> None:
        from app.services.embedding_text import build_resume_embedding_text

        parsed_data = {"skills": ["Python"], "summary": "A very specific profile string."}
        resume_text = build_resume_embedding_text(parsed_data)

        role = await _make_role(session, required_skills=["Python"])
        # Pre-seed the role's embedding with exactly what the fake provider
        # will deterministically produce for the resume's own profile text,
        # so raw cosine similarity is exactly 1.0 — a fully controlled,
        # non-flaky way to test the "great match" end of the scale.
        role.embedding = fake_embeddings._vector(resume_text)
        await session.commit()

        resume = await _make_resume(session, role=role, raw_text="x", parsed_data=parsed_data)

        await scoring_service.score_resume(resume.id)

        score = (
            await session.execute(
                select(ResumeScore).where(ResumeScore.resume_id == resume.id)
            )
        ).scalar_one()
        assert score.semantic_score == 100.0

    async def test_role_and_jd_embeddings_are_averaged(
        self, session, parsing_env, fake_embeddings
    ) -> None:
        role = await _make_role(session, required_skills=["Python"])
        role.embedding = fake_embeddings._vector("role text")
        jd = JobDescription(
            title="AI Engineer",
            raw_text="...",
            parsed_data={"required_skills": []},
            embedding=fake_embeddings._vector("jd text"),
        )
        session.add(jd)
        await session.flush()

        batch = ScreeningBatch(
            job_role_id=role.id,
            job_description_id=jd.id,
            name="batch",
            status=BatchStatus.CREATED,
        )
        session.add(batch)
        await session.commit()

        resume = await _make_resume(
            session,
            role=role,
            raw_text="x",
            parsed_data={"skills": ["Python"], "summary": "profile"},
            batch_id=batch.id,
            job_description_id=jd.id,
        )

        await scoring_service.score_resume(resume.id)

        score = (
            await session.execute(
                select(ResumeScore).where(ResumeScore.resume_id == resume.id)
            )
        ).scalar_one()
        # Not comparing an exact value (the merge math is already covered by
        # TestAverageVector) — just confirming the JD path is actually taken
        # rather than silently falling back to the role alone.
        assert score.semantic_score is not None
        assert score.job_description_id == jd.id


class TestSuggestions:
    async def test_suggests_missing_skills_and_experience(
        self, session, parsing_env
    ) -> None:
        role = await _make_role(session, required_skills=["Python", "Docker"])
        resume = await _make_resume(
            session,
            role=role,
            raw_text="x",
            parsed_data={"skills": []},  # nothing matches, no experience data either
        )

        await scoring_service.score_resume(resume.id)

        score = (
            await session.execute(
                select(ResumeScore).where(ResumeScore.resume_id == resume.id)
            )
        ).scalar_one()
        joined = " ".join(score.suggestions)
        assert "Python" in joined and "Docker" in joined
        assert any("years of experience" in s for s in score.suggestions)
        assert any("work experience section" in s for s in score.suggestions)
        assert any("educational background" in s for s in score.suggestions)

    async def test_leads_with_an_affirmation_of_matched_skills(
        self, session, parsing_env
    ) -> None:
        role = await _make_role(session, required_skills=["Python", "SQL"])
        resume = await _make_resume(
            session, role=role, raw_text="x", parsed_data={"skills": ["Python"]}
        )

        await scoring_service.score_resume(resume.id)

        score = (
            await session.execute(
                select(ResumeScore).where(ResumeScore.resume_id == resume.id)
            )
        ).scalar_one()
        assert score.suggestions[0].startswith("Good news first:")
        assert "Python" in score.suggestions[0]

    async def test_only_the_affirmation_when_everything_matches(
        self, session, parsing_env
    ) -> None:
        role = await _make_role(session, required_skills=["Python"], ats_keywords=["python"])
        resume = await _make_resume(
            session,
            role=role,
            raw_text="Expert in python development.",
            parsed_data={
                "skills": ["Python"],
                "total_experience_years": 5,
                "experience": [{"title": "Engineer", "company": "Acme"}],
                "education": [{"degree": "BSc", "institution": "MIT"}],
            },
        )

        await scoring_service.score_resume(resume.id)

        score = (
            await session.execute(
                select(ResumeScore).where(ResumeScore.resume_id == resume.id)
            )
        ).scalar_one()
        assert len(score.suggestions) == 1
        assert score.suggestions[0].startswith("Good news first:")


class TestJobDescriptionMerge:
    async def test_jd_required_skills_are_merged_into_scoring(
        self, session, parsing_env
    ) -> None:
        role = await _make_role(session, required_skills=["Python"])
        jd = JobDescription(
            title="AI Engineer",
            raw_text="...",
            parsed_data={"required_skills": ["Kubernetes"]},
        )
        session.add(jd)
        await session.flush()

        batch = ScreeningBatch(
            job_role_id=role.id,
            job_description_id=jd.id,
            name="batch",
            status=BatchStatus.CREATED,
        )
        session.add(batch)
        await session.commit()

        resume = await _make_resume(
            session,
            role=role,
            raw_text="x",
            parsed_data={"skills": ["Python"]},
            batch_id=batch.id,
            job_description_id=jd.id,
        )

        await scoring_service.score_resume(resume.id)

        score = (
            await session.execute(
                select(ResumeScore).where(ResumeScore.resume_id == resume.id)
            )
        ).scalar_one()
        assert score.job_description_id == jd.id
        assert "Kubernetes" in score.missing_skills
        assert score.required_skill_match == 50.0  # 1 of 2 combined required skills


class TestScoringLifecycle:
    async def test_sets_analysis_status_completed(self, session, parsing_env) -> None:
        role = await _make_role(session)
        resume = await _make_resume(session, role=role, raw_text="x", parsed_data={})

        await scoring_service.score_resume(resume.id)
        await session.refresh(resume)

        assert resume.analysis_status == AnalysisStatus.COMPLETED
        assert resume.analysis_error is None

    async def test_rescoring_overwrites_rather_than_duplicates(
        self, session, parsing_env
    ) -> None:
        role = await _make_role(session, required_skills=["Python"])
        resume = await _make_resume(
            session, role=role, raw_text="x", parsed_data={"skills": []}
        )

        await scoring_service.score_resume(resume.id)
        await scoring_service.score_resume(resume.id)

        rows = (
            await session.execute(
                select(ResumeScore).where(ResumeScore.resume_id == resume.id)
            )
        ).scalars().all()
        assert len(rows) == 1

    async def test_missing_resume_id_is_a_noop(self, session, parsing_env) -> None:
        await scoring_service.score_resume(uuid.uuid4())  # must not raise

    async def test_unexpected_exception_marks_failed(
        self, session, parsing_env, monkeypatch
    ) -> None:
        role = await _make_role(session)
        resume = await _make_resume(session, role=role, raw_text="x", parsed_data={})

        def _boom(*args, **kwargs):
            raise RuntimeError("scoring exploded")

        monkeypatch.setattr(scoring_service, "_score_ats_keywords", _boom)

        await scoring_service.score_resume(resume.id)
        await session.refresh(resume)

        assert resume.analysis_status == AnalysisStatus.FAILED
        assert "scoring exploded" in resume.analysis_error
