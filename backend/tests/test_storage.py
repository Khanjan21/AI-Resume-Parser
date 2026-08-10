"""Storage-layer tests: hashing, date sharding and traversal protection."""

from __future__ import annotations

import pytest

from app.services.storage import LocalResumeStorage, compute_content_hash


class TestContentHash:
    def test_is_stable_for_identical_bytes(self) -> None:
        assert compute_content_hash(b"abc") == compute_content_hash(b"abc")

    def test_differs_for_different_bytes(self) -> None:
        assert compute_content_hash(b"abc") != compute_content_hash(b"abd")

    def test_is_sha256_length(self) -> None:
        assert len(compute_content_hash(b"abc")) == 64


class TestLocalResumeStorage:
    async def test_save_and_read_round_trip(self, tmp_path) -> None:
        storage = LocalResumeStorage(root=tmp_path)
        _, relative = await storage.save(b"hello resume", ".txt")

        assert storage.exists(relative)
        assert await storage.read(relative) == b"hello resume"

    async def test_shards_by_year_and_month(self, tmp_path) -> None:
        storage = LocalResumeStorage(root=tmp_path)
        _, relative = await storage.save(b"data", ".pdf")

        year, month, filename = relative.split("/")
        assert len(year) == 4 and year.isdigit()
        assert len(month) == 2 and month.isdigit()
        assert filename.endswith(".pdf")

    async def test_identical_content_gets_distinct_paths(self, tmp_path) -> None:
        """Storage never collides; de-duplication is a database concern."""
        storage = LocalResumeStorage(root=tmp_path)
        _, first = await storage.save(b"same", ".txt")
        _, second = await storage.save(b"same", ".txt")
        assert first != second

    async def test_delete_removes_file_and_is_idempotent(self, tmp_path) -> None:
        storage = LocalResumeStorage(root=tmp_path)
        _, relative = await storage.save(b"bye", ".txt")

        assert storage.delete(relative) is True
        assert storage.exists(relative) is False
        assert storage.delete(relative) is False

    @pytest.mark.parametrize(
        "path",
        ["../../../etc/passwd", "..\\..\\windows\\system32", "../outside.txt"],
    )
    def test_rejects_paths_outside_the_root(self, tmp_path, path: str) -> None:
        storage = LocalResumeStorage(root=tmp_path)
        with pytest.raises(ValueError):
            storage.absolute_path(path)

    def test_exists_is_false_for_traversal_attempt(self, tmp_path) -> None:
        storage = LocalResumeStorage(root=tmp_path)
        assert storage.exists("../../../etc/passwd") is False
