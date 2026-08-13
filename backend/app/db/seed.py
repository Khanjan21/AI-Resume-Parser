"""Idempotent seeding of the system job-role catalogue.

Runs on startup (and via `python -m app.db.seed`). System roles are upserted so
that editing the JSON file and restarting is enough to update the catalogue,
while recruiter-created custom roles are never touched.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.job_role import JobRole
from app.services.embedding import get_embedding_provider
from app.services.embedding_text import build_job_role_embedding_text

logger = get_logger(__name__)

SEED_FILE = Path(__file__).resolve().parents[1] / "data" / "job_roles_seed.json"

# Only these keys are copied from the seed file onto the model.
_SEED_FIELDS = (
    "title",
    "category",
    "summary",
    "description",
    "default_level",
    "min_experience_years",
    "max_experience_years",
    "required_skills",
    "preferred_skills",
    "nice_to_have_skills",
    "responsibilities",
    "education",
    "ats_keywords",
    "scoring_weights",
)


def load_seed_roles() -> list[dict[str, Any]]:
    if not SEED_FILE.exists():
        raise FileNotFoundError(f"Job role seed file missing: {SEED_FILE}")
    with SEED_FILE.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("Job role seed file must contain a JSON array")
    return data


async def seed_job_roles(session: AsyncSession) -> tuple[int, int]:
    """Insert missing roles and refresh existing system roles.

    Returns (created_count, updated_count).
    """
    roles = load_seed_roles()
    slugs = [role["slug"] for role in roles]

    existing = (
        await session.execute(select(JobRole).where(JobRole.slug.in_(slugs)))
    ).scalars().all()
    by_slug = {role.slug: role for role in existing}

    created = updated = 0
    needs_embedding: list[JobRole] = []

    for payload in roles:
        slug = payload["slug"]
        fields = {key: payload[key] for key in _SEED_FIELDS if key in payload}
        role = by_slug.get(slug)

        if role is None:
            role = JobRole(slug=slug, is_system=True, is_active=True, **fields)
            session.add(role)
            created += 1
            needs_embedding.append(role)
            continue

        if not role.is_system:
            # A recruiter took over this slug; leave their edits alone.
            continue

        changed = False
        for key, value in fields.items():
            if getattr(role, key) != value:
                setattr(role, key, value)
                changed = True
        if changed:
            updated += 1
        # Covers both "content changed" and "embedding column didn't exist
        # yet when this row was created" (e.g. right after the Day 4
        # migration) — either way, there's nothing current to compare against.
        if changed or role.embedding is None:
            needs_embedding.append(role)

    if needs_embedding:
        await _embed_roles(session, needs_embedding)

    await session.commit()
    logger.info("Job role seed complete: %d created, %d updated", created, updated)
    return created, updated


async def _embed_roles(session: AsyncSession, roles: list[JobRole]) -> None:
    """Batch-embeds every role that's new, changed, or missing an embedding.

    One call to the model for all of them, rather than one per role — batching
    is where local transformer models actually get their speed.
    """
    texts = [
        build_job_role_embedding_text(
            title=role.title,
            summary=role.summary,
            description=role.description,
            required_skills=role.required_skills,
            preferred_skills=role.preferred_skills,
            responsibilities=role.responsibilities,
        )
        for role in roles
    ]
    vectors = await get_embedding_provider().embed(texts)
    for role, vector in zip(roles, vectors):
        role.embedding = vector
    logger.info("Embedded %d job role(s)", len(roles))


async def run_seed() -> None:
    async with AsyncSessionLocal() as session:
        await seed_job_roles(session)


if __name__ == "__main__":  # pragma: no cover - manual entry point
    # Standalone runs bypass app startup, so set up logging here or the summary
    # line from seed_job_roles goes nowhere.
    from app.core.logging import configure_logging

    configure_logging()
    asyncio.run(run_seed())
