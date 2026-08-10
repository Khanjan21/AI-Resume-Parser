"""Shared response envelopes."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class MessageResponse(BaseModel):
    message: str


class PageMeta(BaseModel):
    total: int = Field(..., description="Total rows matching the query")
    limit: int
    offset: int
    has_more: bool


class Page(BaseModel, Generic[T]):
    items: list[T]
    meta: PageMeta


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str
    database: str
