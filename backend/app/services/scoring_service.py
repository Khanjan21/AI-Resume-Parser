"""Day 3: ATS keyword coverage, required-skill match, experience fit.

Pure rule-based scoring — no LLM, no embeddings (that's Day 4's semantic
layer). Runs as a `BackgroundTask` straight after a resume finishes parsing,
mirroring `parsing_service`: it opens its own database session rather than
reusing the caller's, since by the time it runs the original request has
already returned its response.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.enums import AnalysisStatus
from app.models.job_description import JobDescription
from app.models.job_role import JobRole
from app.models.resume import Resume
from app.models.resume_score import ResumeScore
from app.models.screening_batch import ScreeningBatch

logger = get_logger(__name__)

# Suggestions read as a short coaching checklist — specific enough to act on,
# not so long it stops being skimmable.
_MAX_SUGGESTIONS = 6
_MAX_MISSING_SKILLS_IN_SUGGESTION = 5

# The components already available today. `semantic` (Day 4) isn't in here —
# its share of the configured weights gets dropped and the rest renormalised,
# rather than every score being capped until that lands.
_SCORED_COMPONENTS = ("ats", "required_skills", "experience")


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


def _score_overall(
    *, ats_score: float, required_skill_match: float, experience_match: float, weights: dict
) -> float:
    """Blend today's components using a role's configured weights.

    A role with no configured weights (e.g. a bare-bones custom role) falls
    back to a plain average rather than dividing by zero.
    """
    components = {
        "ats": ats_score,
        "required_skills": required_skill_match,
        "experience": experience_match,
    }
    component_weights = {key: float(weights.get(key, 0.0)) for key in _SCORED_COMPONENTS}
    total_weight = sum(component_weights.values())

    if total_weight <= 0:
        return round(sum(components.values()) / len(components), 1)

    weighted_sum = sum(components[key] * component_weights[key] for key in _SCORED_COMPONENTS)
    return round(weighted_sum / total_weight, 1)


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
            final_score = _score_overall(
                ats_score=ats_score,
                required_skill_match=required_skill_match,
                experience_match=experience_match,
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
            score.final_score = final_score
            score.suggestions = suggestions
            score.scored_at = _utcnow()

            if existing is None:
                session.add(score)

            resume.analysis_status = AnalysisStatus.COMPLETED
            resume.analysis_error = None

        except Exception as exc:  # noqa: BLE001 - one bad resume must not crash the worker
            logger.exception("Unexpected scoring failure for resume %s", resume_id)
            resume.analysis_status = AnalysisStatus.FAILED
            resume.analysis_error = f"Unexpected error: {exc}"[:2000]

        await session.commit()
