"""Upload validation: extension, size, and real content sniffing.

The declared Content-Type from a browser is advisory at best, so every file is
checked against its magic bytes before it is written to disk.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import FileTooLargeError, UnsupportedFileTypeError, ValidationError

ALLOWED_EXTENSIONS: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
}

# Leading bytes that must be present for binary formats.
_MAGIC_PREFIXES: dict[str, tuple[bytes, ...]] = {
    ".pdf": (b"%PDF-",),
    # DOCX is a ZIP container; the three prefixes cover normal, empty and
    # spanned archives produced by different writers.
    ".docx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
}

_READ_CHUNK = 1024 * 1024  # 1 MiB
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class ValidatedUpload:
    """A file that passed every check, held in memory ready to persist."""

    content: bytes
    original_filename: str
    safe_filename: str
    extension: str
    content_type: str
    size_bytes: int


def sanitize_filename(filename: str) -> str:
    """Strip directory components and unsafe characters from a client filename."""
    # Defend against both POSIX and Windows separators plus traversal.
    base = filename.replace("\\", "/").split("/")[-1].strip()
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    base = _UNSAFE_FILENAME_CHARS.sub("_", base).strip("._")
    return base[:180] or "upload"


def get_extension(filename: str) -> str:
    name = sanitize_filename(filename).lower()
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[1]


def _looks_like_text(content: bytes) -> bool:
    if b"\x00" in content[:8192]:
        return False
    try:
        content[:8192].decode("utf-8")
    except UnicodeDecodeError:
        try:
            content[:8192].decode("latin-1")
        except UnicodeDecodeError:
            return False
    return True


def verify_magic_bytes(content: bytes, extension: str) -> bool:
    prefixes = _MAGIC_PREFIXES.get(extension)
    if prefixes is None:
        return _looks_like_text(content)
    return any(content.startswith(prefix) for prefix in prefixes)


async def read_upload(file: UploadFile) -> bytes:
    """Read an UploadFile with a hard size ceiling.

    Reads one chunk beyond the limit so an oversized file is rejected without
    buffering the whole thing.
    """
    limit = settings.max_upload_size_bytes
    chunks: list[bytes] = []
    total = 0

    await file.seek(0)
    while chunk := await file.read(_READ_CHUNK):
        total += len(chunk)
        if total > limit:
            raise FileTooLargeError(
                f"'{file.filename}' exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB limit.",
                details={"max_size_mb": settings.MAX_UPLOAD_SIZE_MB},
            )
        chunks.append(chunk)

    return b"".join(chunks)


async def validate_upload(file: UploadFile) -> ValidatedUpload:
    """Run every check and return the file's bytes plus normalised metadata."""
    if not file.filename:
        raise ValidationError("Uploaded file has no filename.")

    safe_name = sanitize_filename(file.filename)
    extension = get_extension(file.filename)

    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileTypeError(
            f"'{file.filename}' has an unsupported type. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            details={"allowed_extensions": sorted(ALLOWED_EXTENSIONS)},
        )

    content = await read_upload(file)

    if not content:
        raise ValidationError(f"'{file.filename}' is empty.")

    if not verify_magic_bytes(content, extension):
        raise UnsupportedFileTypeError(
            f"'{file.filename}' does not appear to be a valid {extension} file.",
            details={"declared_extension": extension},
        )

    return ValidatedUpload(
        content=content,
        original_filename=file.filename[:255],
        safe_filename=safe_name,
        extension=extension,
        content_type=ALLOWED_EXTENSIONS[extension],
        size_bytes=len(content),
    )
