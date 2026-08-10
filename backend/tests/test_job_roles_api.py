"""API tests for the job-role catalogue."""

from __future__ import annotations

from httpx import AsyncClient

SEEDED_SLUGS = {
    "ai-engineer",
    "ml-engineer",
    "python-developer",
    "full-stack-developer",
    "data-scientist",
    "business-analyst",
}


class TestListJobRoles:
    async def test_returns_every_seeded_role(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/job-roles")
        assert response.status_code == 200

        body = response.json()
        assert SEEDED_SLUGS.issubset({item["slug"] for item in body["items"]})
        assert body["meta"]["total"] >= len(SEEDED_SLUGS)

    async def test_paginates(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/job-roles", params={"limit": 2, "offset": 0})
        body = response.json()

        assert len(body["items"]) == 2
        assert body["meta"]["has_more"] is True

    async def test_filters_by_search_term(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/job-roles", params={"search": "engineer"})
        slugs = {item["slug"] for item in response.json()["items"]}

        assert "ai-engineer" in slugs
        assert "business-analyst" not in slugs

    async def test_filters_by_category(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/job-roles", params={"category": "business"})
        assert {item["slug"] for item in response.json()["items"]} == {"business-analyst"}

    async def test_rejects_out_of_range_limit(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/job-roles", params={"limit": 500})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "request_validation_error"


class TestGetJobRole:
    async def test_fetches_by_slug_with_full_detail(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/job-roles/ai-engineer")
        assert response.status_code == 200

        body = response.json()
        assert body["title"] == "AI Engineer"
        assert "Python" in body["required_skills"]
        assert body["ats_keywords"]
        assert body["is_system"] is True

    async def test_fetches_by_uuid(self, client: AsyncClient, ai_role_id: str) -> None:
        response = await client.get(f"/api/v1/job-roles/{ai_role_id}")
        assert response.status_code == 200
        assert response.json()["slug"] == "ai-engineer"

    async def test_scoring_weights_sum_to_one(self, client: AsyncClient) -> None:
        """Day 5 combines these into a final score, so they must be normalised."""
        response = await client.get("/api/v1/job-roles")
        for item in response.json()["items"]:
            detail = (await client.get(f"/api/v1/job-roles/{item['slug']}")).json()
            weights = detail["scoring_weights"]
            if weights:
                assert abs(sum(weights.values()) - 1.0) < 1e-6, item["slug"]

    async def test_unknown_slug_returns_404(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/job-roles/nope")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


class TestCreateJobRole:
    async def test_creates_custom_role_with_generated_slug(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/job-roles",
            json={"title": "Cloud Architect", "required_skills": ["AWS", "Terraform"]},
        )
        assert response.status_code == 201

        body = response.json()
        assert body["slug"] == "cloud-architect"
        assert body["is_system"] is False

    async def test_rejects_duplicate_slug(self, client: AsyncClient) -> None:
        payload = {"title": "Site Reliability Engineer"}
        assert (await client.post("/api/v1/job-roles", json=payload)).status_code == 201

        conflict = await client.post("/api/v1/job-roles", json=payload)
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "duplicate_resource"

    async def test_rejects_blank_title(self, client: AsyncClient) -> None:
        response = await client.post("/api/v1/job-roles", json={"title": "x"})
        assert response.status_code == 422
