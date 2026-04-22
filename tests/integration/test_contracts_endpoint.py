import pytest


@pytest.mark.asyncio
async def test_health_endpoint(async_client):
    async with async_client as client:
        response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_job_not_found(async_client):
    async with async_client as client:
        response = await client.get("/api/v1/contracts/nonexistent_id/status")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"


@pytest.mark.asyncio
async def test_upload_rejects_non_pdf(async_client):
    async with async_client as client:
        response = await client.post(
            "/api/v1/contracts",
            files={"file": ("test.txt", b"not a pdf", "text/plain")},
            headers={"X-LLM-Provider": "ollama"},
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_PDF"


@pytest.mark.asyncio
async def test_upload_contract_returns_job_id(async_client, sample_pdf_bytes):
    async with async_client as client:
        response = await client.post(
            "/api/v1/contracts",
            files={"file": ("test.pdf", sample_pdf_bytes, "application/pdf")},
            data={"language": "en", "contract_type": "rental"},
            headers={"X-LLM-Provider": "ollama"},
        )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "queued"
    assert data["job_id"].startswith("job_")


@pytest.mark.asyncio
async def test_estimate_returns_cost(async_client, sample_pdf_bytes):
    async with async_client as client:
        response = await client.post(
            "/api/v1/contracts/estimate",
            files={"file": ("test.pdf", sample_pdf_bytes, "application/pdf")},
            headers={"X-LLM-Provider": "claude"},
        )
    assert response.status_code == 200
    data = response.json()
    assert "estimated_tokens" in data
    assert data["provider"] == "claude"
    assert data["estimated_cost_usd"] is not None


@pytest.mark.asyncio
async def test_estimate_ollama_is_free(async_client, sample_pdf_bytes):
    async with async_client as client:
        response = await client.post(
            "/api/v1/contracts/estimate",
            files={"file": ("test.pdf", sample_pdf_bytes, "application/pdf")},
            headers={"X-LLM-Provider": "ollama"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["estimated_cost_usd"] is None
    assert "free" in data["note"].lower()


@pytest.mark.asyncio
async def test_session_not_found_for_conversation(async_client):
    async with async_client as client:
        response = await client.post(
            "/api/v1/contracts/job_doesnotexist/messages",
            json={"message": "What does clause 7 mean?"},
            headers={"X-LLM-Provider": "ollama"},
        )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"
