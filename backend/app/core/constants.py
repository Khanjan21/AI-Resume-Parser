"""Tiny, dependency-free constants shared across modules that must NOT import
heavy packages just to see them (models, Alembic migrations, schemas).

`EMBEDDING_DIMENSIONS` in particular must stay out of anything that imports
`sentence-transformers`/`torch` transitively — those take several seconds to
import, which is fine for the embedding service itself but not for every
model file, every test, and every Alembic run.
"""

from __future__ import annotations

EMBEDDING_DIMENSIONS = 384  # BAAI/bge-small-en-v1.5's output size
