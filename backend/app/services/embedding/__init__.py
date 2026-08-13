"""Embedding provider package — import `get_embedding_provider`, not a concrete class."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.services.embedding.base import EmbeddingError, EmbeddingProvider
from app.services.embedding.bge_provider import BgeEmbeddingProvider

__all__ = ["EmbeddingError", "EmbeddingProvider", "BgeEmbeddingProvider", "get_embedding_provider"]


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    return BgeEmbeddingProvider(settings.EMBEDDING_MODEL)
