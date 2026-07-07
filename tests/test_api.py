"""
Test the FastAPI application endpoints.
"""

import uuid
import pytest
from httpx import AsyncClient


def _unique_domain():
    return f"test-{uuid.uuid4().hex[:8]}.com"


def _unique_project(domain=None):
    return {
        "domain": domain or _unique_domain(),
        "target_country": "DE",
        "target_language": "de",
        "target_cities": ["Köln", "Bonn"],
        "services": ["App Entwicklung", "Flutter Entwicklung"],
        "competitors": ["competitor-test.de"],
    }


@pytest.mark.asyncio
async def test_root_health(async_client: AsyncClient):
    """Test the root health endpoint."""
    response = await async_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Neuronal SEO API"
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_check(async_client: AsyncClient):
    """Test the /health endpoint with DB check."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "database" in data


@pytest.mark.asyncio
async def test_create_project(async_client: AsyncClient, sample_project_data):
    """Test creating a project via the API."""
    data = _unique_project()
    response = await async_client.post("/api/v1/projects/", json=data)
    assert response.status_code == 201
    result = response.json()
    assert result["domain"] == data["domain"]
    assert "id" in result


@pytest.mark.asyncio
async def test_list_projects(async_client: AsyncClient):
    """Test listing projects."""
    # Create a project first
    await async_client.post("/api/v1/projects/", json=_unique_project())

    response = await async_client.get("/api/v1/projects/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


@pytest.mark.asyncio
async def test_get_project(async_client: AsyncClient):
    """Test getting a single project."""
    data = _unique_project()
    create_resp = await async_client.post("/api/v1/projects/", json=data)
    assert create_resp.status_code == 201
    project_id = create_resp.json()["id"]

    response = await async_client.get(f"/api/v1/projects/{project_id}")
    assert response.status_code == 200
    result = response.json()
    assert result["domain"] == data["domain"]


@pytest.mark.asyncio
async def test_project_not_found(async_client: AsyncClient):
    """Test 404 for non-existent project."""
    response = await async_client.get("/api/v1/projects/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_project_stats(async_client: AsyncClient):
    """Test project statistics endpoint."""
    create_resp = await async_client.post("/api/v1/projects/", json=_unique_project())
    assert create_resp.status_code == 201
    project_id = create_resp.json()["id"]

    response = await async_client.get(f"/api/v1/projects/{project_id}/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_pages" in data
    assert "total_keywords" in data


@pytest.mark.asyncio
async def test_add_keywords(async_client: AsyncClient):
    """Test adding keywords to a project."""
    create_resp = await async_client.post("/api/v1/projects/", json=_unique_project())
    assert create_resp.status_code == 201
    project_id = create_resp.json()["id"]

    kw_data = {
        "keywords": ["app entwicklung köln", "flutter entwickler", "mvp agentur"],
        "language": "de",
        "country": "DE",
        "city": "Köln",
        "source": "test",
    }

    response = await async_client.post(
        f"/api/v1/keywords/{project_id}/batch", json=kw_data
    )
    assert response.status_code == 201
    data = response.json()
    assert data["added"] == 3


@pytest.mark.asyncio
async def test_list_keywords(async_client: AsyncClient):
    """Test listing keywords."""
    create_resp = await async_client.post("/api/v1/projects/", json=_unique_project())
    assert create_resp.status_code == 201
    project_id = create_resp.json()["id"]

    # Add keywords
    await async_client.post(
        f"/api/v1/keywords/{project_id}/batch",
        json={"keywords": ["test keyword 1", "test keyword 2"]},
    )

    response = await async_client.get(f"/api/v1/keywords/{project_id}")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2


@pytest.mark.asyncio
async def test_similarity_search(async_client: AsyncClient):
    """Test the embedding similarity search endpoint."""
    create_resp = await async_client.post("/api/v1/projects/", json=_unique_project())
    assert create_resp.status_code == 201
    project_id = create_resp.json()["id"]

    response = await async_client.post(
        f"/api/v1/embeddings/{project_id}/search",
        json={"text": "app entwicklung", "object_type": "keyword", "limit": 5},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_analysis_endpoints(async_client: AsyncClient):
    """Test that analysis endpoints accept requests."""
    create_resp = await async_client.post("/api/v1/projects/", json=_unique_project())
    assert create_resp.status_code == 201
    project_id = create_resp.json()["id"]

    endpoints = [
        f"/api/v1/analysis/{project_id}/cluster",
        f"/api/v1/analysis/{project_id}/classify-intent",
        f"/api/v1/analysis/{project_id}/map-pages",
        f"/api/v1/analysis/{project_id}/detect-gaps",
        f"/api/v1/analysis/{project_id}/suggest-links",
        f"/api/v1/analysis/{project_id}/score-opportunities",
    ]

    for endpoint in endpoints:
        response = await async_client.post(endpoint)
        assert response.status_code == 200, f"Failed: {endpoint}"
        data = response.json()
        assert data["status"] == "accepted"


@pytest.mark.asyncio
async def test_delete_project(async_client: AsyncClient):
    """Test deleting a project."""
    create_resp = await async_client.post("/api/v1/projects/", json=_unique_project())
    assert create_resp.status_code == 201
    project_id = create_resp.json()["id"]

    response = await async_client.delete(f"/api/v1/projects/{project_id}")
    assert response.status_code == 200

    # Verify it's gone
    response = await async_client.get(f"/api/v1/projects/{project_id}")
    assert response.status_code == 404
