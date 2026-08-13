"""BGE-small-en-v1.5 via sentence-transformers — runs locally on CPU.

Free, no API key, no rate limits. Empirically confirmed (see Day 4 notes in
the README) that whole-document embeddings from this model cleanly separate a
matching resume/role pair (~0.85 cosine similarity) from a mismatched-field
resume (~0.60) from unrelated text (~0.39) — the reliable use case for a
general-purpose sentence embedding model. Bare skill-name-to-skill-name
comparison does *not* separate reliably (tested and rejected — see README),
which is why semantic matching here operates on whole profile/role text only.
"""

from __future__ import annotations

import asyncio

from app.core.logging import get_logger
from app.services.embedding.base import EmbeddingError, EmbeddingProvider

logger = get_logger(__name__)

_MODEL_NAME = "BAAI/bge-small-en-v1.5"
_DIMENSIONS = 384


class BgeEmbeddingProvider(EmbeddingProvider):
    dimensions = _DIMENSIONS

    def __init__(self, model_name: str = _MODEL_NAME) -> None:
        # `sentence_transformers` (and the torch/transformers chain under it)
        # is imported here, not at module level — importing it eagerly added
        # a 40+ second tax to *every* import of this module, including plain
        # `app.main`/test collection that never touches embeddings at all.
        # Construction itself then loads model weights from disk (~7s warm,
        # ~30s on the very first run when it has to download) — see
        # get_embedding_provider, called once at app startup specifically to
        # pay this cost before any request needs it, not on a user's first score.
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model %s...", model_name)
        try:
            self._model = SentenceTransformer(model_name)
        except Exception as exc:  # noqa: BLE001 - surfaced as a clear domain error
            raise EmbeddingError(f"Could not load embedding model: {exc}") from exc
        logger.info("Embedding model %s ready.", model_name)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            return await asyncio.to_thread(self._encode, texts)
        except Exception as exc:  # noqa: BLE001
            raise EmbeddingError(f"Embedding failed: {exc}") from exc

    def _encode(self, texts: list[str]) -> list[list[float]]:
        # normalize_embeddings=True makes the dot product equal cosine
        # similarity directly, which is what pgvector's <#> (inner product)
        # operator computes — no separate normalisation needed at query time.
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return vectors.tolist()
