"""Resume file storage.

A thin interface over the local filesystem so the backing store can be swapped
for S3/GCS later without touching the API layer. Files are sharded by upload
date to keep directory listings small.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiofiles

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def compute_content_hash(content: bytes) -> str:
    """SHA-256 of the raw bytes — the identity used for de-duplication."""
    return hashlib.sha256(content).hexdigest()


class LocalResumeStorage:
    """Stores resumes under `<STORAGE_DIR>/resumes/<YYYY>/<MM>/<uuid>.<ext>`."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or settings.resume_dir

    def ensure_ready(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def _build_target(self, extension: str) -> tuple[Path, str]:
        now = datetime.now(timezone.utc)
        directory = self.root / f"{now.year:04d}" / f"{now.month:02d}"
        directory.mkdir(parents=True, exist_ok=True)
        stored_filename = f"{uuid.uuid4().hex}{extension}"
        return directory / stored_filename, stored_filename

    async def save(self, content: bytes, extension: str) -> tuple[str, str]:
        """Persist bytes and return (stored_filename, relative_path)."""
        self.ensure_ready()
        target, stored_filename = self._build_target(extension)

        async with aiofiles.open(target, "wb") as handle:
            await handle.write(content)

        relative = target.relative_to(self.root).as_posix()
        logger.debug("Stored resume at %s (%d bytes)", relative, len(content))
        return stored_filename, relative

    def absolute_path(self, relative_path: str) -> Path:
        """Resolve a stored relative path, refusing anything outside the root."""
        root = self.root.resolve()
        candidate = (root / relative_path).resolve()
        if not candidate.is_relative_to(root):
            raise ValueError(f"Refusing to access path outside storage root: {relative_path}")
        return candidate

    def exists(self, relative_path: str) -> bool:
        try:
            return self.absolute_path(relative_path).is_file()
        except ValueError:
            return False

    async def read(self, relative_path: str) -> bytes:
        async with aiofiles.open(self.absolute_path(relative_path), "rb") as handle:
            return await handle.read()

    def delete(self, relative_path: str) -> bool:
        """Remove a stored file. Returns False if it was already gone."""
        try:
            path = self.absolute_path(relative_path)
        except ValueError:
            return False
        if not path.is_file():
            return False
        path.unlink()
        return True


resume_storage = LocalResumeStorage()
