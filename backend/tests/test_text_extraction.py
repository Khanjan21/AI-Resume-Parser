"""Unit tests for local text extraction — no database, no LLM."""

from __future__ import annotations

import pytest

from app.services.text_extraction import TextExtractionError, extract_text
from tests.conftest import build_pdf_bytes


class TestPdfExtraction:
    def test_extracts_text_from_a_valid_pdf(self) -> None:
        content = build_pdf_bytes("JANE DOE\nData Scientist\nSkills: Python, SQL")
        result = extract_text(content, ".pdf")

        assert "JANE DOE" in result.text
        assert "Skills: Python, SQL" in result.text
        assert result.page_count == 1
        assert result.word_count > 0

    def test_rejects_a_pdf_with_no_page_tree(self) -> None:
        broken = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EOF\n"
        with pytest.raises(TextExtractionError):
            extract_text(broken, ".pdf")

    def test_rejects_garbage_bytes(self) -> None:
        with pytest.raises(TextExtractionError):
            extract_text(b"not a pdf at all", ".pdf")


class TestDocxExtraction:
    def test_extracts_paragraphs(self) -> None:
        content = (
            (
                __import__("pathlib").Path(__file__).resolve().parents[1]
                / "sample_data"
                / "rahul_sharma_ai_engineer.docx"
            ).read_bytes()
        )
        result = extract_text(content, ".docx")

        assert "RAHUL SHARMA" in result.text
        assert result.page_count is None
        assert result.word_count > 0

    def test_rejects_a_non_docx_zip(self) -> None:
        import io
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr("readme.txt", "not a real docx")

        with pytest.raises(TextExtractionError):
            extract_text(buf.getvalue(), ".docx")


class TestPlainTextExtraction:
    def test_decodes_utf8(self) -> None:
        result = extract_text("café résumé".encode("utf-8"), ".txt")
        assert result.text == "café résumé"

    def test_falls_back_to_latin1_on_bad_utf8(self) -> None:
        result = extract_text(b"caf\xe9", ".txt")
        assert result.text == "café"

    def test_rejects_empty_file(self) -> None:
        with pytest.raises(TextExtractionError):
            extract_text(b"   ", ".txt")

    def test_md_uses_the_same_path_as_txt(self) -> None:
        result = extract_text(b"# Heading\n\nBody text", ".md")
        assert "Heading" in result.text


class TestDispatch:
    def test_unknown_extension_raises(self) -> None:
        with pytest.raises(TextExtractionError):
            extract_text(b"whatever", ".xyz")

    def test_extension_matching_is_case_insensitive(self) -> None:
        result = extract_text(b"hello world", ".TXT")
        assert result.text == "hello world"
