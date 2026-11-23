import json
from pathlib import Path

import httpx
import openai
import pytest
from fastapi.testclient import TestClient

from app.embedding_pipeline.embedder import ChunkTooLargeError
from app.embedding_pipeline.router import get_embedder
from app.embedding_pipeline.schemas import EmbeddedChunk
from app.main import app

SAMPLE = Path(__file__).resolve().parents[2] / "data" / "budgets_sample.json"


class FakeEmbedder:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.received: list = []

    def embed_many(self, chunks):
        self.received = chunks
        if self.error:
            raise self.error
        return [EmbeddedChunk(**chunk.model_dump(), embedding=[0.1, 0.2]) for chunk in chunks]


@pytest.fixture
def embedder():
    fake = FakeEmbedder()
    app.dependency_overrides[get_embedder] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


client = TestClient(app, raise_server_exceptions=False)


def test_ingest_returns_embedded_chunks_and_stats(embedder, make_budget_payload) -> None:
    body = {"budgets": [make_budget_payload("BUD-A"), make_budget_payload("BUD-B")]}

    response = client.post("/embeddings/ingest", json=body)

    assert response.status_code == 200
    data = response.json()
    assert [c["chunk_id"] for c in data["chunks"]] == ["BUD-A::AUTH-001", "BUD-B::AUTH-001"]
    assert data["chunks"][0]["embedding"] == [0.1, 0.2]
    assert data["chunks"][0]["metadata"]["client_sector"] == "finance"
    tokens = sum(c["token_count"] for c in data["chunks"])
    assert data["stats"] == {
        "total_budgets": 2,
        "total_chunks": 2,
        "total_tokens": tokens,
        "estimated_cost_usd": pytest.approx(tokens * 0.02 / 1_000_000, abs=1e-6),
    }


def test_the_sample_dataset_is_valid_and_ingestable(embedder) -> None:
    budgets = json.loads(SAMPLE.read_text(encoding="utf-8"))

    response = client.post("/embeddings/ingest", json={"budgets": budgets})

    assert response.status_code == 200, response.text
    assert len(budgets) == 15
    stats = response.json()["stats"]
    assert stats["total_budgets"] == 15
    assert stats["total_chunks"] == sum(len(b["components"]) for b in budgets)
    chunk_ids = [c["chunk_id"] for c in response.json()["chunks"]]
    assert len(set(chunk_ids)) == len(chunk_ids)


def test_the_sample_covers_the_four_sectors_and_several_stacks() -> None:
    budgets = json.loads(SAMPLE.read_text(encoding="utf-8"))

    assert {b["client_metadata"]["sector"] for b in budgets} == {
        "finance",
        "ecommerce",
        "healthcare",
        "industrial",
    }
    assert len({b["main_technology"] for b in budgets}) >= 5


@pytest.mark.parametrize(
    "mutate",
    [
        lambda body: body.pop("budgets"),
        lambda body: body.update(budgets=[]),
        lambda body: body["budgets"][0].pop("project_summary"),
        lambda body: body["budgets"][0]["components"][0].update(complexity="extreme"),
        lambda body: body["budgets"][0]["components"][0].update(estimated_hours=-5),
        lambda body: body["budgets"][0].update(components=[]),
        lambda body: body.update(budgets=body["budgets"] * 2),  # mismo budget_id::component_id repetido
    ],
)
def test_invalid_bodies_are_rejected_with_422(embedder, make_budget_payload, mutate) -> None:
    body = {"budgets": [make_budget_payload()]}
    mutate(body)

    response = client.post("/embeddings/ingest", json=body)

    assert response.status_code == 422
    assert embedder.received == []


def test_an_oversized_chunk_is_a_422_not_a_server_error(make_budget_payload) -> None:
    app.dependency_overrides[get_embedder] = lambda: FakeEmbedder(ChunkTooLargeError("chunk B::C has too many tokens"))
    try:
        response = client.post("/embeddings/ingest", json={"budgets": [make_budget_payload()]})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "too many tokens" in response.json()["detail"]


def test_openai_failures_return_a_generic_500_without_leaking_details(make_budget_payload) -> None:
    secret = "Incorrect API key provided: sk-proj-abc123"
    request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    error = openai.AuthenticationError(secret, response=httpx.Response(401, request=request), body=None)
    app.dependency_overrides[get_embedder] = lambda: FakeEmbedder(error)
    try:
        response = client.post("/embeddings/ingest", json={"budgets": [make_budget_payload()]})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json() == {"detail": "Embedding service error"}
    assert "sk-proj" not in response.text


def test_missing_api_key_is_a_503(monkeypatch, make_budget_payload) -> None:
    from app.embedding_pipeline import router

    monkeypatch.setattr(router.settings, "openai_api_key", None)

    response = client.post("/embeddings/ingest", json={"budgets": [make_budget_payload()]})

    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]


def test_the_endpoint_is_listed_in_the_openapi_docs() -> None:
    assert "/embeddings/ingest" in client.get("/openapi.json").json()["paths"]
