"""API tests for the candidate single-upload flow."""

from __future__ import annotations

import uuid

from httpx import AsyncClient


def file_payload(name: str, content: bytes, content_type: str) -> dict:
    return {"file": (name, content, content_type)}


class TestCandidateUpload:
    async def test_uploads_a_resume(
        self, client: AsyncClient, ai_role_id: str, resume_txt
    ) -> None:
        response = await client.post(
            "/api/v1/resumes",
            data={"job_role_id": ai_role_id},
            files=file_payload(*resume_txt),
        )
        assert response.status_code == 201

        body = response.json()
        assert body["duplicate"] is False
        assert body["resume"]["upload_source"] == "candidate"
        assert body["resume"]["parse_status"] == "pending"
        assert body["resume"]["job_role_id"] == ai_role_id
        assert len(body["resume"]["content_hash"]) == 64

    async def test_accepts_pdf(
        self, client: AsyncClient, ai_role_id: str, resume_pdf
    ) -> None:
        response = await client.post(
            "/api/v1/resumes",
            data={"job_role_id": ai_role_id},
            files=file_payload(*resume_pdf),
        )
        assert response.status_code == 201
        assert response.json()["resume"]["content_type"] == "application/pdf"

    async def test_same_file_same_role_is_deduplicated(
        self, client: AsyncClient, ai_role_id: str, resume_txt
    ) -> None:
        first = await client.post(
            "/api/v1/resumes",
            data={"job_role_id": ai_role_id},
            files=file_payload(*resume_txt),
        )
        second = await client.post(
            "/api/v1/resumes",
            data={"job_role_id": ai_role_id},
            files=file_payload(*resume_txt),
        )

        assert second.json()["duplicate"] is True
        assert second.json()["resume"]["id"] == first.json()["resume"]["id"]

    async def test_same_file_different_role_creates_new_record(
        self, client: AsyncClient, ai_role_id: str, resume_txt
    ) -> None:
        other_role = (await client.get("/api/v1/job-roles/ml-engineer")).json()["id"]

        first = await client.post(
            "/api/v1/resumes",
            data={"job_role_id": ai_role_id},
            files=file_payload(*resume_txt),
        )
        second = await client.post(
            "/api/v1/resumes",
            data={"job_role_id": other_role},
            files=file_payload(*resume_txt),
        )

        assert second.json()["duplicate"] is False
        assert second.json()["resume"]["id"] != first.json()["resume"]["id"]

    async def test_rejects_unsupported_type(
        self, client: AsyncClient, ai_role_id: str
    ) -> None:
        response = await client.post(
            "/api/v1/resumes",
            data={"job_role_id": ai_role_id},
            files=file_payload("virus.exe", b"MZ\x90\x00", "application/octet-stream"),
        )
        assert response.status_code == 415
        assert response.json()["error"]["code"] == "unsupported_file_type"

    async def test_rejects_file_lying_about_its_type(
        self, client: AsyncClient, ai_role_id: str
    ) -> None:
        response = await client.post(
            "/api/v1/resumes",
            data={"job_role_id": ai_role_id},
            files=file_payload("fake.pdf", b"plain text", "application/pdf"),
        )
        assert response.status_code == 415

    async def test_rejects_unknown_job_role(
        self, client: AsyncClient, resume_txt
    ) -> None:
        response = await client.post(
            "/api/v1/resumes",
            data={"job_role_id": str(uuid.uuid4())},
            files=file_payload(*resume_txt),
        )
        assert response.status_code == 404


class TestResumeRetrieval:
    async def test_lists_and_filters_resumes(
        self, client: AsyncClient, ai_role_id: str, resume_txt
    ) -> None:
        await client.post(
            "/api/v1/resumes",
            data={"job_role_id": ai_role_id},
            files=file_payload(*resume_txt),
        )

        listed = await client.get("/api/v1/resumes", params={"job_role_id": ai_role_id})
        assert listed.json()["meta"]["total"] == 1

        filtered = await client.get(
            "/api/v1/resumes", params={"upload_source": "recruiter"}
        )
        assert filtered.json()["meta"]["total"] == 0

    async def test_downloads_original_bytes(
        self, client: AsyncClient, ai_role_id: str, resume_txt
    ) -> None:
        created = await client.post(
            "/api/v1/resumes",
            data={"job_role_id": ai_role_id},
            files=file_payload(*resume_txt),
        )
        resume_id = created.json()["resume"]["id"]

        download = await client.get(f"/api/v1/resumes/{resume_id}/download")
        assert download.status_code == 200
        assert download.content == resume_txt[1]

    async def test_deletes_resume(
        self, client: AsyncClient, ai_role_id: str, resume_txt
    ) -> None:
        created = await client.post(
            "/api/v1/resumes",
            data={"job_role_id": ai_role_id},
            files=file_payload(*resume_txt),
        )
        resume_id = created.json()["resume"]["id"]

        assert (await client.delete(f"/api/v1/resumes/{resume_id}")).status_code == 200
        assert (await client.get(f"/api/v1/resumes/{resume_id}")).status_code == 404

    async def test_unknown_resume_returns_404(self, client: AsyncClient) -> None:
        response = await client.get(f"/api/v1/resumes/{uuid.uuid4()}")
        assert response.status_code == 404
