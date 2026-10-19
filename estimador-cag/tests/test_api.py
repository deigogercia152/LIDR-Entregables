from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.routers import estimations

client = TestClient(app)


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_estimation_endpoint_returns_model_response(monkeypatch) -> None:
    def fake_process_estimation(transcription: str) -> str:
        assert transcription == "Necesito una aplicación para inventario."
        return "Estimación de prueba"

    monkeypatch.setattr(
        estimations,
        "process_estimation_request",
        fake_process_estimation,
    )

    response = client.post(
        "/api/v1/estimate",
        json={"transcription": "Necesito una aplicación para inventario."},
    )

    assert response.status_code == 200
    assert response.json() == {
        "estimation": "Estimación de prueba",
        "model": estimations.settings.llm_model,
        "provider": estimations.settings.llm_provider,
    }


def test_estimation_endpoint_rejects_blank_transcription() -> None:
    response = client.post("/api/v1/estimate", json={"transcription": "   "})

    assert response.status_code == 422


def test_openapi_docs_are_available() -> None:
    docs_response = client.get("/docs")
    response = client.get("/openapi.json")

    assert docs_response.status_code == 200
    assert response.status_code == 200
    assert "/api/v1/estimate" in response.json()["paths"]


def test_required_project_structure_and_transcription_exist() -> None:
    project_root = Path(__file__).resolve().parents[1]
    required_paths = (
        "app/main.py",
        "app/config.py",
        "app/routers/estimations.py",
        "app/services/llm_services.py",
        "app/context/examples.py",
        ".env.example",
        ".gitignore",
        "pyproject.toml",
        "README.md",
        "data/transcripcion_reunion.txt",
    )

    assert all((project_root / path).is_file() for path in required_paths)
    assert "*.env" in (project_root / ".gitignore").read_text(encoding="utf-8")


def test_cag_prompt_includes_static_examples_and_request() -> None:
    from app.context.examples import get_estimation_examples
    from app.services.llm_services import build_system_message, build_user_message

    examples = get_estimation_examples()
    system_message = build_system_message()
    user_message = build_user_message("Reunión de prueba")

    assert len(examples) >= 2
    assert all(example["meeting_summary"].strip() for example in examples)
    assert all("Coste estimado:" in example["estimation"] for example in examples)
    assert all(example["meeting_summary"].strip() in system_message for example in examples)
    assert all(example["estimation"].strip() in system_message for example in examples)
    assert "horas y coste" in system_message
    assert "Reunión de prueba" in user_message
