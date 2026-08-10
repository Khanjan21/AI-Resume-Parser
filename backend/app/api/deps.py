"""Reusable FastAPI dependencies.

Note: this module deliberately omits `from __future__ import annotations`.
PEP 563 string annotations turn the nested `Annotated[int, Query(...)]` hints on
the class-based `Pagination` dependency into forward refs that FastAPI cannot
resolve, which surfaces as a PydanticUserError at request time.
"""

import uuid
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.job_role import JobRole
from app.models.resume import Resume
from app.models.screening_batch import ScreeningBatch

DbSession = Annotated[AsyncSession, Depends(get_db)]


class Pagination:
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.limit = limit
        self.offset = offset


PaginationDep = Annotated[Pagination, Depends()]


async def get_job_role_or_404(session: AsyncSession, role_id: uuid.UUID) -> JobRole:
    role = await session.get(JobRole, role_id)
    if role is None:
        raise NotFoundError(f"Job role {role_id} not found.")
    return role


async def get_job_role_by_slug_or_404(session: AsyncSession, slug: str) -> JobRole:
    stmt = select(JobRole).where(JobRole.slug == slug)
    role = (await session.execute(stmt)).scalar_one_or_none()
    if role is None:
        raise NotFoundError(f"Job role '{slug}' not found.")
    return role


async def get_resume_or_404(session: AsyncSession, resume_id: uuid.UUID) -> Resume:
    stmt = (
        select(Resume)
        .where(Resume.id == resume_id)
        .options(selectinload(Resume.batch), selectinload(Resume.job_role))
    )
    resume = (await session.execute(stmt)).scalar_one_or_none()
    if resume is None:
        raise NotFoundError(f"Resume {resume_id} not found.")
    return resume


async def get_batch_or_404(
    session: AsyncSession, batch_id: uuid.UUID, *, with_resumes: bool = False
) -> ScreeningBatch:
    options = [selectinload(ScreeningBatch.job_role)]
    if with_resumes:
        options.append(selectinload(ScreeningBatch.resumes))

    stmt = select(ScreeningBatch).where(ScreeningBatch.id == batch_id).options(*options)
    batch = (await session.execute(stmt)).scalar_one_or_none()
    if batch is None:
        raise NotFoundError(f"Screening batch {batch_id} not found.")
    return batch
