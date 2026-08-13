"""Provider-agnostic interface for text embeddings.

Mirrors `app.services.llm`'s shape deliberately: everything downstream talks to
this interface via `get_embedding_provider()`, never to a concrete model class,
so swapping BGE for E5 or a hosted embedding API later is a new class and a
one-line factory change, not a rewrite of the scoring service.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.exceptions import AppError


class EmbeddingError(AppError):
    """Raised when a provider fails to produce an embedding."""

    status_code = 502
    code = "embedding_failed"


class EmbeddingProvider(ABC):
    dimensions: int

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts, returning one vector per input, in order.

        Batching matters: embedding N texts in one call is far cheaper than N
        separate calls for local transformer models, so callers scoring a
        recruiter batch should collect texts and embed them together where
        practical.
        """
        raise NotImplementedError
