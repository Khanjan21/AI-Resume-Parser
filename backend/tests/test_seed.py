"""Tests for the job-role seeder's embedding backfill (Day 4 addition).

Covers only what Day 4 changed — role upsert logic itself is already
exercised indirectly by every test that uses the `client`/`session` fixtures
(they all depend on a freshly seeded catalogue via `test_engine`).
"""

from __future__ import annotations

from sqlalchemy import select

from app.db.seed import seed_job_roles
from app.models.job_role import JobRole


class TestSeedEmbeddings:
    async def test_fresh_seed_embeds_every_role(self, session, fake_embeddings) -> None:
        # `test_engine` already ran seed_job_roles once (with fake_embeddings
        # patched) as part of its own setup, so this just confirms the result.
        roles = (await session.execute(select(JobRole))).scalars().all()
        assert len(roles) == 6
        assert all(role.embedding is not None for role in roles)

    async def test_reseeding_unchanged_roles_does_not_recompute_embeddings(
        self, session, fake_embeddings
    ) -> None:
        fake_embeddings.calls.clear()

        created, updated = await seed_job_roles(session)

        assert created == 0
        assert updated == 0
        assert fake_embeddings.calls == []  # nothing needed re-embedding

    async def test_changing_a_role_triggers_re_embedding(
        self, session, fake_embeddings, monkeypatch
    ) -> None:
        # Mutating the DB row directly wouldn't test this correctly — the
        # next seed pass treats the JSON file as the source of truth and
        # would just overwrite the mutation right back to the original
        # content (and thus the original embedding). The seed file itself
        # has to change.
        from app.db import seed as seed_module

        role = (
            await session.execute(select(JobRole).where(JobRole.slug == "ai-engineer"))
        ).scalar_one()
        original_embedding = role.embedding

        modified_roles = [dict(r) for r in seed_module.load_seed_roles()]
        for role_data in modified_roles:
            if role_data["slug"] == "ai-engineer":
                role_data["summary"] = "A deliberately different summary to force a re-embed."
        monkeypatch.setattr(seed_module, "load_seed_roles", lambda: modified_roles)

        fake_embeddings.calls.clear()
        await seed_module.seed_job_roles(session)

        await session.refresh(role)
        assert role.summary == "A deliberately different summary to force a re-embed."
        assert fake_embeddings.calls  # the changed role was re-embedded
        assert role.embedding != original_embedding
