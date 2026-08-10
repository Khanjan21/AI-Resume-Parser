"""Unit tests for upload validation — no database or HTTP involved."""

from __future__ import annotations

import io

import pytest
from fastapi import UploadFile

from app.core.exceptions import (
    FileTooLargeError,
    UnsupportedFileTypeError,
    ValidationError,
)
from app.services.file_validation import (
    get_extension,
    sanitize_filename,
    validate_upload,
    verify_magic_bytes,
)


def make_upload(filename: str, content: bytes) -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(content))


class TestSanitizeFilename:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("resume.pdf", "resume.pdf"),
            # Only the basename survives, so traversal segments are dropped.
            ("../../etc/passwd", "passwd"),
            (r"C:\Users\me\cv.docx", "cv.docx"),
            ("my resume (final).pdf", "my_resume_final_.pdf"),
            ("résumé.pdf", "resume.pdf"),
            ("...", "upload"),
        ],
    )
    def test_strips_paths_and_unsafe_characters(self, raw: str, expected: str) -> None:
        assert sanitize_filename(raw) == expected

    def test_truncates_very_long_names(self) -> None:
        assert len(sanitize_filename("a" * 500 + ".pdf")) <= 180


class TestGetExtension:
    @pytest.mark.parametrize(
        ("filename", "expected"),
        [
            ("cv.PDF", ".pdf"),
            ("cv.docx", ".docx"),
            ("archive.tar.gz", ".gz"),
            ("noextension", ""),
        ],
    )
    def test_extension_is_lowercased_and_last_segment(
        self, filename: str, expected: str
    ) -> None:
        assert get_extension(filename) == expected


class TestMagicBytes:
    def test_accepts_real_pdf_header(self) -> None:
        assert verify_magic_bytes(b"%PDF-1.7\n...", ".pdf")

    def test_rejects_text_masquerading_as_pdf(self) -> None:
        assert not verify_magic_bytes(b"just text", ".pdf")

    def test_accepts_zip_container_for_docx(self) -> None:
        assert verify_magic_bytes(b"PK\x03\x04rest", ".docx")

    def test_rejects_binary_for_text(self) -> None:
        assert not verify_magic_bytes(b"\x00\x01\x02binary", ".txt")

    def test_accepts_utf8_text(self) -> None:
        assert verify_magic_bytes("naïve résumé".encode(), ".txt")


class TestValidateUpload:
    async def test_accepts_valid_text_resume(self) -> None:
        result = await validate_upload(make_upload("cv.txt", b"Python developer"))
        assert result.extension == ".txt"
        assert result.content_type == "text/plain"
        assert result.size_bytes == 16

    async def test_rejects_disallowed_extension(self) -> None:
        with pytest.raises(UnsupportedFileTypeError):
            await validate_upload(make_upload("malware.exe", b"MZ\x90\x00"))

    async def test_rejects_content_type_mismatch(self) -> None:
        with pytest.raises(UnsupportedFileTypeError):
            await validate_upload(make_upload("fake.pdf", b"not a pdf at all"))

    async def test_rejects_empty_file(self) -> None:
        with pytest.raises(ValidationError):
            await validate_upload(make_upload("empty.txt", b""))

    async def test_rejects_oversized_file(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "app.services.file_validation.settings.MAX_UPLOAD_SIZE_MB", 0.001
        )
        with pytest.raises(FileTooLargeError):
            await validate_upload(make_upload("big.txt", b"x" * 5000))
