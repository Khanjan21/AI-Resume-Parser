"""Job-role catalogue endpoints (shared by both flows)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status
from slugify import slugify
from sqlalchemy import func, select

from app.api.deps import DbSession, PaginationDep, get_job_role_by_slug_or_404
from app.core.exceptions import DuplicateResourceError
from app.models.job_role import JobRole
from app.schemas.common import Page, PageMeta
from app.schemas.job_role import JobRoleCreate, JobRoleDetail, JobRoleSummary

router = APIRouter(prefix="/job-roles", tags=["job-roles"])


@router.get("", response_model=Page[JobRoleSummary], summary="List job roles")
async def list_job_roles(
    session: DbSession,
    pagination: PaginationDep,
    category: str | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    search: str | None = Query(default=None, min_length=1, max_length=100),
) -> Page[JobRoleSummary]:
    filters = []
    if not include_inactive:
        filters.append(JobRole.is_active.is_(True))
    if category:
        filters.append(JobRole.category == category)
    if search:
        filters.append(JobRole.title.ilike(f"%{search}%"))

    total = await session.scalar(
        select(func.count()).select_from(JobRole).where(*filters)
    )

    stmt = (
        select(JobRole)
        .where(*filters)
        .order_by(JobRole.category, JobRole.title)
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    roles = (await session.execute(stmt)).scalars().all()

    return Page[JobRoleSummary](
        items=[JobRoleSummary.model_validate(role) for role in roles],
        meta=PageMeta(
            total=total or 0,
            limit=pagination.limit,
            offset=pagination.offset,
            has_more=pagination.offset + len(roles) < (total or 0),
        ),
    )


@router.get(
    "/{role_ref}",
    response_model=JobRoleDetail,
    summary="Get a job role by slug or id",
)
async def get_job_role(role_ref: str, session: DbSession) -> JobRoleDetail:
    """Accepts either the human-friendly slug (`ai-engineer`) or the UUID."""
    try:
        role_id = uuid.UUID(role_ref)
    except ValueError:
        role = await get_job_role_by_slug_or_404(session, role_ref)
    else:
        role = await session.get(JobRole, role_id)
        if role is None:
            role = await get_job_role_by_slug_or_404(session, role_ref)

    return JobRoleDetail.model_validate(role)


@router.post(
    "",
    response_model=JobRoleDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a custom job role",
)
async def create_job_role(payload: JobRoleCreate, session: DbSession) -> JobRoleDetail:
    slug = slugify(payload.title)[:80]

    exists = await session.scalar(select(JobRole.id).where(JobRole.slug == slug))
    if exists:
        raise DuplicateResourceError(
            f"A job role with slug '{slug}' already exists.", details={"slug": slug}
        )

    role = JobRole(slug=slug, is_system=False, is_active=True, **payload.model_dump())
    session.add(role)
    await session.flush()
    return JobRoleDetail.model_validate(role)
