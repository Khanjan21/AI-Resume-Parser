"""Aggregates every v1 endpoint module."""

from fastapi import APIRouter

from app.api.v1.endpoints import batches, job_descriptions, job_roles, resumes

api_router = APIRouter()
api_router.include_router(job_roles.router)
api_router.include_router(job_descriptions.router)
api_router.include_router(resumes.router)
api_router.include_router(batches.router)
