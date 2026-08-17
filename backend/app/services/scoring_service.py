"""Day 3 (ATS keyword coverage, required-skill match, experience fit) plus
Day 4's semantic layer (whole-profile embedding similarity via pgvector).

Runs as a `BackgroundTask` straight after a resume finishes parsing, mirroring
`parsing_service`: it opens its own database session rather than reusing the
caller's, since by the time it runs the original request has already returned
its response.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.enums import AnalysisStatus, ShortlistCategory
from app.models.job_description import JobDescription
from app.models.job_role import JobRole
from app.models.resume import Resume
from app.models.resume_score import ResumeScore
from app.models.screening_batch import ScreeningBatch
from app.services.embedding import EmbeddingError, get_embedding_provider
from app.services.embedding_text import (
    build_job_role_embedding_text,
    build_resume_embedding_text,
)

logger = get_logger(__name__)

# Suggestions read as a short coaching checklist — specific enough to act on,
# not so long it stops being skimmable.
_MAX_SUGGESTIONS = 6
_MAX_MISSING_SKILLS_IN_SUGGESTION = 5

# Empirically calibrated against BAAI/bge-small-en-v1.5 (see the Day 4 section
# in the README): a matching resume/role pair lands around 0.85 raw cosine
# similarity, a wrong-field resume around 0.60, unrelated text around 0.39.
# Raw cosine similarity from this model never spans the full 0-1 range for
# related text, so a plain `similarity * 100` would make even irrelevant
# resumes look like a ~40% match. This floor/ceiling rescale stretches the
# realistic range into an intuitive 0-100 score instead.
_SEMANTIC_SIMILARITY_FLOOR = 0.35
_SEMANTIC_SIMILARITY_CEILING = 0.90

# Day 5: recruiter-facing shortlist bucket, derived from `final_score`. Fixed
# global cutoffs rather than a per-role config — nothing in the spec called
# for per-role tuning, and these can move if Day 7's evaluation benchmark
# shows they should, without touching the role catalogue.
_STRONG_MATCH_THRESHOLD = 75.0
_CONSIDER_THRESHOLD = 45.0


def _normalise(skill: str) -> str:
    return skill.strip().lower()


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = _normalise(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _score_ats_keywords(raw_text: str, keywords: list[str]) -> tuple[float, list[str]]:
    """Classic ATS behaviour: literal, case-insensitive substring scanning."""
    if not keywords:
        # Nothing to check against isn't the resume's fault.
        return 100.0, []

    haystack = raw_text.lower()
    matched = [kw for kw in keywords if kw.lower() in haystack]
    score = (len(matched) / len(keywords)) * 100
    return round(score, 1), matched


def _score_skill_match(
    resume_skills: list[str], required_skills: list[str], preferred_skills: list[str]
) -> tuple[float, list[str], list[str]]:
    resume_normalised = {_normalise(s) for s in resume_skills}

    matched_required = [s for s in required_skills if _normalise(s) in resume_normalised]
    missing_required = [s for s in required_skills if _normalise(s) not in resume_normalised]
    matched_preferred = [s for s in preferred_skills if _normalise(s) in resume_normalised]

    score = (
        (len(matched_required) / len(required_skills)) * 100 if required_skills else 100.0
    )
    matched_skills = _dedupe_preserve_order(matched_required + matched_preferred)
    return round(score, 1), matched_skills, missing_required


def _score_experience(
    candidate_years: float | None, min_years: float, max_years: float | None
) -> float:
    if candidate_years is None:
        return 50.0  # Unstated, not necessarily absent — stay neutral.
    if candidate_years >= min_years:
        return 100.0
    if min_years <= 0:
        return 100.0
    return round(max(0.0, candidate_years / min_years) * 100, 1)


def _score_semantic(resume_vector: list[float], target_vector: list[float]) -> float:
    """Cosine similarity, rescaled into an intuitive 0-100 range.

    Both vectors come out of the embedding model already normalised, so their
    dot product *is* the cosine similarity — no separate normalisation step
    needed here.
    """
    similarity = sum(a * b for a, b in zip(resume_vector, target_vector))
    span = _SEMANTIC_SIMILARITY_CEILING - _SEMANTIC_SIMILARITY_FLOOR
    scaled = (similarity - _SEMANTIC_SIMILARITY_FLOOR) / span * 100
    return round(max(0.0, min(100.0, scaled)), 1)


def _average_vector(vectors: list[list[float]]) -> list[float]:
    """Element-wise mean — used when both a role and a linked JD have an
    embedding, so scoring reflects both rather than picking one arbitrarily."""
    length = len(vectors)
    return [sum(v[i] for v in vectors) / length for i in range(len(vectors[0]))]


def _score_overall(
    *,
    ats_score: float,
    required_skill_match: float,
    experience_match: float,
    semantic_score: float | None,
    weights: dict,
) -> float:
    """Blend the available components using a role's configured weights.

    `semantic_score` is only present once an embedding comparison succeeded;
    when it's None (no role/JD embedding available yet), its configured
    weight share is dropped and the rest renormalised, rather than the score
    being capped for a reason that has nothing to do with the resume. A role
    with no configured weights at all (e.g. a bare-bones custom role) falls
    back to a plain average rather than dividing by zero.
    """
    components = {
        "ats": ats_score,
        "required_skills": required_skill_match,
        "experience": experience_match,
    }
    if semantic_score is not None:
        components["semantic"] = semantic_score

    component_weights = {key: float(weights.get(key, 0.0)) for key in components}
    total_weight = sum(component_weights.values())

    if total_weight <= 0:
        return round(sum(components.values()) / len(components), 1)

    weighted_sum = sum(components[key] * component_weights[key] for key in components)
    return round(weighted_sum / total_weight, 1)


def _categorize(final_score: float | None) -> str | None:
    """Buckets a resume into a shortlist category for the recruiter view.

    Stays `None` alongside `final_score` when nothing could be computed yet
    (e.g. a role with no configured weights and no components at all) —
    there's no reasonable bucket for a resume that hasn't been scored.
    """
    if final_score is None:
        return None
    if final_score >= _STRONG_MATCH_THRESHOLD:
        return ShortlistCategory.STRONG_MATCH
    if final_score >= _CONSIDER_THRESHOLD:
        return ShortlistCategory.CONSIDER
    return ShortlistCategory.WEAK_MATCH


def _build_suggestions(
    *,
    matched_skills: list[str],
    missing_skills: list[str],
    ats_score: float,
    matched_ats_keywords: list[str],
    ats_keywords: list[str],
    candidate_years: float | None,
    has_experience_entries: bool,
    has_education_entries: bool,
) -> list[str]:
    suggestions: list[str] = []

    # Lead with what's already working — this reads as coaching, not just a
    # deficiency list, and it's honestly informative: a reviewer scanning
    # quickly benefits from knowing what to look for just as much as a
    # candidate benefits from knowing what landed.
    if matched_skills:
        sample = ", ".join(matched_skills[:_MAX_MISSING_SKILLS_IN_SUGGESTION])
        suggestions.append(
            f"Good news first: {sample} all came through clearly, and they're "
            "exactly what this role is looking for. Keep them visible near the "
            "top of your resume — in a skills summary or your opening line — "
            "since that's usually the first thing a reviewer or ATS scan checks."
        )

    if missing_skills:
        sample = ", ".join(missing_skills[:_MAX_MISSING_SKILLS_IN_SUGGESTION])
        suggestions.append(
            f"You're missing a few skills this role looks for: {sample}. If "
            "you've genuinely worked with any of these, add them along with a "
            "specific example — even one line showing how you used it can "
            "meaningfully lift your match."
        )

    if ats_score < 50:
        missing_keywords = [kw for kw in ats_keywords if kw not in matched_ats_keywords]
        if missing_keywords:
            sample = ", ".join(missing_keywords[:_MAX_MISSING_SKILLS_IN_SUGGESTION])
            suggestions.append(
                f"Automated screening for this role commonly looks for terms "
                f"like {sample}. Weaving a few of these into your summary or "
                "experience bullets, wherever they honestly apply, tends to "
                "improve how ATS systems rank a resume."
            )

    if candidate_years is None:
        suggestions.append(
            "Your total years of experience isn't clearly stated. Spelling it "
            "out explicitly (e.g. '4 years of experience in AI engineering') "
            "makes it far easier for both automated systems and recruiters to "
            "size up your background at a glance."
        )

    if not has_experience_entries:
        suggestions.append(
            "Add a dedicated work experience section with job titles, company "
            "names, dates, and 2-3 measurable achievements per role — this is "
            "one of the highest-impact sections for both ATS systems and human "
            "reviewers."
        )

    if not has_education_entries:
        suggestions.append(
            "Add your educational background, including degree, institution "
            "and graduation year — many screening pipelines check for this early."
        )

    return suggestions[:_MAX_SUGGESTIONS]


async def _resolve_job_description(session, resume: Resume) -> JobDescription | None:
    """A resume's scoring context comes from its role, plus — if the recruiter
    linked one — the specific JD its batch is being screened against."""
    if resume.batch_id is None:
        return None
    batch = await session.get(ScreeningBatch, resume.batch_id)
    if batch is None or batch.job_description_id is None:
        return None
    return await session.get(JobDescription, batch.job_description_id)


async def _compute_semantic_score(
    *,
    resume: Resume,
    job_role: JobRole | None,
    job_description: JobDescription | None,
    parsed: dict,
) -> float | None:
    """Embeds the resume's profile text, backfills the role's embedding if
    it's missing (custom roles created via the API aren't embedded at
    creation time), and returns a 0-100 similarity score — or None if there's
    nothing usable to compare against yet (e.g. a role whose embedding failed
    to compute, or a resume with no extractable profile text).
    """
    provider = get_embedding_provider()

    resume_text = build_resume_embedding_text(parsed)
    resume.embedding = (
        (await provider.embed([resume_text]))[0] if resume_text.strip() else None
    )

    if job_role is not None and job_role.embedding is None:
        role_text = build_job_role_embedding_text(
            title=job_role.title,
            summary=job_role.summary,
            description=job_role.description,
            required_skills=job_role.required_skills,
            preferred_skills=job_role.preferred_skills,
            responsibilities=job_role.responsibilities,
        )
        job_role.embedding = (await provider.embed([role_text]))[0]

    # If a batch links a specific JD, blend its embedding with the role's
    # rather than picking one — same "extend, don't replace" philosophy
    # already used for merging required-skill lists.
    targets = [
        vector
        for vector in (
            job_role.embedding if job_role is not None else None,
            job_description.embedding if job_description is not None else None,
        )
        if vector is not None
    ]

    if resume.embedding is None or not targets:
        return None

    target_vector = targets[0] if len(targets) == 1 else _average_vector(targets)
    return _score_semantic(resume.embedding, target_vector)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def score_resume(resume_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as session:
        resume = await session.get(Resume, resume_id)
        if resume is None:
            logger.warning("score_resume: resume %s no longer exists", resume_id)
            return

        resume.analysis_status = AnalysisStatus.PROCESSING
        await session.commit()

        try:
            job_role = (
                await session.get(JobRole, resume.job_role_id)
                if resume.job_role_id
                else None
            )
            job_description = await _resolve_job_description(session, resume)

            required_skills = list(job_role.required_skills) if job_role else []
            preferred_skills = list(job_role.preferred_skills) if job_role else []
            ats_keywords = list(job_role.ats_keywords) if job_role else []
            min_years = job_role.min_experience_years if job_role else 0.0
            max_years = job_role.max_experience_years if job_role else None

            if job_description and job_description.parsed_data:
                jd_data = job_description.parsed_data
                required_skills = _dedupe_preserve_order(
                    required_skills + list(jd_data.get("required_skills") or [])
                )
                preferred_skills = _dedupe_preserve_order(
                    preferred_skills + list(jd_data.get("preferred_skills") or [])
                )
                if jd_data.get("min_experience_years") is not None:
                    min_years = jd_data["min_experience_years"]
                if jd_data.get("max_experience_years") is not None:
                    max_years = jd_data["max_experience_years"]

            parsed = resume.parsed_data or {}
            resume_skills = list(parsed.get("skills") or [])
            candidate_years = parsed.get("total_experience_years")

            ats_score, matched_ats_keywords = _score_ats_keywords(
                resume.raw_text or "", ats_keywords
            )
            required_skill_match, matched_skills, missing_skills = _score_skill_match(
                resume_skills, required_skills, preferred_skills
            )
            experience_match = _score_experience(candidate_years, min_years, max_years)
            semantic_score = await _compute_semantic_score(
                resume=resume,
                job_role=job_role,
                job_description=job_description,
                parsed=parsed,
            )
            final_score = _score_overall(
                ats_score=ats_score,
                required_skill_match=required_skill_match,
                experience_match=experience_match,
                semantic_score=semantic_score,
                weights=job_role.scoring_weights if job_role else {},
            )

            suggestions = _build_suggestions(
                matched_skills=matched_skills,
                missing_skills=missing_skills,
                ats_score=ats_score,
                matched_ats_keywords=matched_ats_keywords,
                ats_keywords=ats_keywords,
                candidate_years=candidate_years,
                has_experience_entries=bool(parsed.get("experience")),
                has_education_entries=bool(parsed.get("education")),
            )

            existing = (
                await session.execute(
                    select(ResumeScore).where(ResumeScore.resume_id == resume.id)
                )
            ).scalar_one_or_none()
            score = existing or ResumeScore(resume_id=resume.id)

            score.job_role_id = resume.job_role_id
            score.job_description_id = job_description.id if job_description else None
            score.ats_score = ats_score
            score.matched_ats_keywords = matched_ats_keywords
            score.required_skill_match = required_skill_match
            score.matched_skills = matched_skills
            score.missing_skills = missing_skills
            score.experience_match = experience_match
            score.candidate_experience_years = candidate_years
            score.semantic_score = semantic_score
            score.final_score = final_score
            score.category = _categorize(final_score)
            score.suggestions = suggestions
            score.scored_at = _utcnow()

            if existing is None:
                session.add(score)

            resume.analysis_status = AnalysisStatus.COMPLETED
            resume.analysis_error = None

        except EmbeddingError as exc:
            logger.info("Scoring failed for resume %s: %s", resume_id, exc)
            resume.analysis_status = AnalysisStatus.FAILED
            resume.analysis_error = str(exc)[:2000]

        except Exception as exc:  # noqa: BLE001 - one bad resume must not crash the worker
            logger.exception("Unexpected scoring failure for resume %s", resume_id)
            resume.analysis_status = AnalysisStatus.FAILED
            resume.analysis_error = f"Unexpected error: {exc}"[:2000]

        await session.commit()
