from pathlib import Path

import httpx
import pytest
from streamlit.testing.v1 import AppTest

from app.schemas import DetailLevel, OutputFormat, ProjectType

APP_PATH = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
DESCRIPTION = "Una tienda online de cerámica artesanal con pasarela de pago y blog."


def _request() -> httpx.Request:
    return httpx.Request("POST", "http://test/api/v1/estimate")


@pytest.fixture
def captured_posts(monkeypatch) -> list[dict]:
    calls: list[dict] = []

    def fake_post(url: str, json: dict, timeout: float) -> httpx.Response:
        calls.append({"url": url, "json": json})
        return httpx.Response(
            200,
            json={"text": "## Estimación de prueba", "prompt_version": "v1"},
            request=_request(),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    return calls


def _fill_form(app: AppTest, description: str = DESCRIPTION) -> AppTest:
    app.text_area(key="description").set_value(description)
    app.selectbox(key="project_type").set_value(ProjectType.WEB_SAAS)
    app.radio(key="detail_level").set_value(DetailLevel.DETAILED)
    app.selectbox(key="output_format").set_value(OutputFormat.PHASES_TABLE)
    return app


def _run_app() -> AppTest:
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    assert not app.exception
    return app


def test_form_posts_typed_request_and_shows_estimation(captured_posts: list[dict]) -> None:
    app = _run_app()
    assert not app.chat_input

    _fill_form(app).button[0].click().run()

    assert not app.exception
    assert len(captured_posts) == 1
    assert captured_posts[0]["url"].endswith("/api/v1/estimate")
    assert captured_posts[0]["json"] == {
        "description": DESCRIPTION,
        "project_type": "web_saas",
        "detail_level": "detailed",
        "output_format": "phases_table",
    }
    assert any("## Estimación de prueba" in md.value for md in app.markdown)
    assert app.session_state.last_result["prompt_version"] == "v1"


def test_form_rejects_short_description_without_calling_service(
    captured_posts: list[dict],
) -> None:
    app = _run_app()

    _fill_form(app, description="Muy corta").button[0].click().run()

    assert not app.exception
    assert captured_posts == []
    assert "20" in app.error[0].value


def test_form_shows_service_error(monkeypatch) -> None:
    def failing_post(url: str, json: dict, timeout: float) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error", request=_request())

    monkeypatch.setattr(httpx, "post", failing_post)
    app = _run_app()

    _fill_form(app).button[0].click().run()

    assert not app.exception
    assert "500" in app.error[0].value
    assert app.session_state.last_result is None


def test_form_shows_connection_error(monkeypatch) -> None:
    def unreachable_post(url: str, json: dict, timeout: float) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=_request())

    monkeypatch.setattr(httpx, "post", unreachable_post)
    app = _run_app()

    _fill_form(app).button[0].click().run()

    assert not app.exception
    assert "No se pudo conectar" in app.error[0].value
