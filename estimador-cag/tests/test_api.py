from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.prompts.loader import render_estimation_prompt
from app.routers import estimations
from app.schemas import EstimationRequest
from app.services.providers.i_llm_provider import ILLMProvider

client = TestClient(app)

VALID_BODY = {
    "description": "Necesitamos una aplicación web para gestionar el inventario de 3 almacenes.",
    "project_type": "web_saas",
    "detail_level": "medium",
    "output_format": "line_items",
}


class FakeProvider(ILLMProvider):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def process_chat(self, system_message: str, messages: list[dict[str, str]]) -> str:
        assert [m["role"] for m in messages] == ["user"]
        self.calls.append((system_message, messages[0]["content"]))
        return "Estimación de prueba"

    def stream_message(self, system_message: str, user_message: str):
        raise AssertionError("el endpoint no usa streaming")


@pytest.fixture
def fake_provider(monkeypatch) -> FakeProvider:
    provider = FakeProvider()
    monkeypatch.setattr(estimations, "get_llm_provider", lambda: provider)
    return provider


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_estimate_returns_text_and_prompt_version(fake_provider: FakeProvider) -> None:
    response = client.post("/api/v1/estimate", json=VALID_BODY)

    assert response.status_code == 200
    assert response.json() == {"text": "Estimación de prueba", "prompt_version": "v1"}


def test_estimate_sends_rendered_system_and_user_as_separate_messages(
    fake_provider: FakeProvider,
) -> None:
    client.post("/api/v1/estimate", json=VALID_BODY)

    expected = render_estimation_prompt(EstimationRequest(**VALID_BODY), version="v1")
    assert fake_provider.calls == [expected]
    system, user = fake_provider.calls[0]
    assert VALID_BODY["description"] in user
    assert VALID_BODY["description"] not in system


def test_estimate_uses_prompt_version_query_param(fake_provider: FakeProvider) -> None:
    response = client.post("/api/v1/estimate?prompt_version=v2", json=VALID_BODY)

    assert response.status_code == 200
    assert response.json() == {"text": "Estimación de prueba", "prompt_version": "v2"}
    expected = render_estimation_prompt(EstimationRequest(**VALID_BODY), version="v2")
    assert fake_provider.calls == [expected]


@pytest.mark.parametrize("version", ["v999", "../estimation"])
def test_estimate_rejects_unknown_prompt_version(
    fake_provider: FakeProvider, version: str
) -> None:
    response = client.post("/api/v1/estimate", params={"prompt_version": version}, json=VALID_BODY)

    assert response.status_code == 422
    assert "Versión de prompt desconocida" in response.json()["detail"]
    assert fake_provider.calls == []


def test_estimate_accepts_reference_projects(fake_provider: FakeProvider) -> None:
    body = {
        **VALID_BODY,
        "reference_projects": [
            {"name": "Inventario v1", "summary": "Web con 2 almacenes", "actual_hours": 180}
        ],
    }

    response = client.post("/api/v1/estimate", json=body)

    assert response.status_code == 200
    _, user = fake_provider.calls[0]
    assert "- Inventario v1: Web con 2 almacenes (180 h reales)" in user


def test_estimate_returns_503_when_provider_is_not_configured(monkeypatch) -> None:
    def missing_key():
        raise ValueError("OPENAI_API_KEY no está configurada.")

    monkeypatch.setattr(estimations, "get_llm_provider", missing_key)

    response = client.post("/api/v1/estimate", json=VALID_BODY)

    assert response.status_code == 503
    assert response.json() == {"detail": "OPENAI_API_KEY no está configurada."}


@pytest.mark.parametrize(
    "overrides",
    [
        {"description": "Demasiado corta"},
        {"description": " " * 25},
        {"description": "   corta con espacios   "},
        {"description": "x" * 2001},
        {"project_type": "MOBILE_APP"},
        {"detail_level": "extreme"},
        {"output_format": None},
    ],
)
def test_estimate_rejects_invalid_body(fake_provider: FakeProvider, overrides: dict) -> None:
    response = client.post("/api/v1/estimate", json={**VALID_BODY, **overrides})

    assert response.status_code == 422
    assert fake_provider.calls == []


def test_openapi_docs_are_available() -> None:
    docs_response = client.get("/docs")
    response = client.get("/openapi.json")

    assert docs_response.status_code == 200
    assert response.status_code == 200
    assert "/api/v1/estimate" in response.json()["paths"]


def test_required_project_structure_exists() -> None:
    project_root = Path(__file__).resolve().parents[1]
    required_paths = (
        "app/main.py",
        "app/config.py",
        "app/schemas.py",
        "app/routers/estimations.py",
        "app/services/llm_services.py",
        "app/prompts/loader.py",
        "app/prompts/estimation/v1/system.j2",
        "app/prompts/estimation/v1/user.j2",
        "app/prompts/estimation/v1/examples.j2",
        "streamlit_app.py",
        ".env.example",
        ".gitignore",
        "pyproject.toml",
        "README.md",
    )

    assert all((project_root / path).is_file() for path in required_paths)
    assert "*.env" in (project_root / ".gitignore").read_text(encoding="utf-8")
