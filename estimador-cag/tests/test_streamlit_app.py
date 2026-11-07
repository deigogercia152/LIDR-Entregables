from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from streamlit.testing.v1 import AppTest

from app.schemas import DetailLevel, OutputFormat, ProjectType

APP_PATH = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
METADATA = {
    "project_name": "Club Pádel",
    "assumed_team_size": 3,
    "mentioned_technologies": ["Django", "Redis"],
    "agreed_scope": "Web de reservas y app móvil",
}


def _request(url: str = "http://test/api/v1") -> httpx.Request:
    return httpx.Request("POST", url)


class FakeService:
    """Sustituye a `httpx.post`: crea sesiones numeradas y responde a las estimaciones."""

    def __init__(self) -> None:
        self.sessions_created = 0
        self.estimates: list[dict] = []
        self.estimate_response = self._ok

    def _ok(self, session_id: str, turn: int) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "text": f"## Estimación {turn}",
                "prompt_version": "v1",
                "session_id": session_id,
                "turn": turn,
                "project_metadata": METADATA if turn > 1 else {**METADATA, "agreed_scope": "Web"},
            },
            request=_request(),
        )

    def __call__(self, url: str, **kwargs) -> httpx.Response:
        if url.endswith("/api/v1/sessions"):
            self.sessions_created += 1
            return httpx.Response(
                201, json={"session_id": f"sesion-{self.sessions_created}"}, request=_request(url)
            )
        session_id = url.split("/sessions/")[1].split("/")[0]
        self.estimates.append({"session_id": session_id, "url": url, **kwargs})
        return self.estimate_response(session_id, len(self.estimates))


@pytest.fixture
def service(monkeypatch) -> FakeService:
    fake = FakeService()
    monkeypatch.setattr(httpx, "post", fake)
    return fake


def _run_app() -> AppTest:
    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    assert not app.exception
    return app


def _send(app: AppTest, transcript: str) -> AppTest:
    app.text_area(key="transcript").set_value(transcript)
    app.button(key="send").click().run()
    assert not app.exception
    return app


def _sidebar_text(app: AppTest) -> str:
    return "\n".join(item.value for item in app.sidebar.markdown)


def test_page_load_creates_one_session_and_keeps_it_across_reruns(service: FakeService) -> None:
    app = _run_app()
    app.run()

    assert service.sessions_created == 1
    assert app.session_state.session_id == "sesion-1"
    assert "Aún no hay datos del proyecto" in app.sidebar.caption[0].value


def test_a_turn_posts_the_typed_params_and_shows_the_conversation(service: FakeService) -> None:
    app = _run_app()
    app.sidebar.selectbox(key="project_type").set_value(ProjectType.MOBILE_APP)
    app.sidebar.radio(key="detail_level").set_value(DetailLevel.DETAILED)
    app.sidebar.selectbox(key="output_format").set_value(OutputFormat.PHASES_TABLE)

    _send(app, "Una app para el club de pádel")

    (call,) = service.estimates
    assert call["url"].endswith("/api/v1/sessions/sesion-1/estimate")
    assert call["data"] == {
        "transcript": "Una app para el club de pádel",
        "project_type": "mobile_app",
        "detail_level": "detailed",
        "output_format": "phases_table",
    }
    assert call.get("files") is None
    assert [m.name for m in app.chat_message] == ["user", "assistant"]
    assert "Una app para el club de pádel" in app.chat_message[0].markdown[0].value
    assert "## Estimación 1" in app.chat_message[1].markdown[0].value


def test_three_turns_keep_the_conversation_and_show_the_project_metadata(
    service: FakeService,
) -> None:
    app = _run_app()

    for transcript in ("Primera reunión", "Segunda reunión", "Tercera reunión"):
        _send(app, transcript)

    assert len(app.chat_message) == 6
    assert {call["session_id"] for call in service.estimates} == {"sesion-1"}
    sidebar = _sidebar_text(app)
    assert "Club Pádel" in sidebar
    assert "Django, Redis" in sidebar
    assert "Web de reservas y app móvil" in sidebar
    assert "3 personas" in sidebar


def test_blank_transcript_is_rejected_without_calling_the_service(service: FakeService) -> None:
    app = _run_app()

    _send(app, "   ")

    assert service.estimates == []
    assert "transcripción" in app.error[0].value


def test_new_conversation_creates_a_fresh_session_and_clears_the_state(
    service: FakeService,
) -> None:
    app = _run_app()
    _send(app, "Primera reunión")

    app.button(key="new_conversation").click().run()

    assert not app.exception
    assert service.sessions_created == 2
    assert app.session_state.session_id == "sesion-2"
    assert len(app.chat_message) == 0
    assert "Aún no hay datos del proyecto" in app.sidebar.caption[0].value


def test_an_expired_session_starts_a_new_one_and_asks_to_resend(service: FakeService) -> None:
    service.estimate_response = lambda session_id, turn: httpx.Response(
        404, json={"detail": "Sesión no encontrada"}, request=_request()
    )
    app = _run_app()

    _send(app, "Primera reunión")

    assert service.sessions_created == 2
    assert app.session_state.session_id == "sesion-2"
    assert "caducó" in app.warning[0].value
    assert len(app.chat_message) == 0


def test_service_errors_are_shown_without_adding_messages(service: FakeService) -> None:
    service.estimate_response = lambda session_id, turn: httpx.Response(
        415, json={"detail": "notas.txt: formato no soportado"}, request=_request()
    )
    app = _run_app()

    _send(app, "Primera reunión")

    assert "415" in app.error[0].value
    assert "formato no soportado" in app.error[0].value
    assert len(app.chat_message) == 0
    assert service.sessions_created == 1


def test_connection_error_when_sending_a_turn(monkeypatch) -> None:
    fake = FakeService()

    def flaky(url: str, **kwargs):
        if url.endswith("/sessions"):
            return fake(url, **kwargs)
        raise httpx.ConnectError("Connection refused", request=_request())

    monkeypatch.setattr(httpx, "post", flaky)
    app = _run_app()

    _send(app, "Primera reunión")

    assert "No se pudo conectar" in app.error[0].value


def test_service_down_on_page_load_shows_an_error_instead_of_crashing(monkeypatch) -> None:
    def unreachable(url: str, **kwargs):
        raise httpx.ConnectError("Connection refused", request=_request())

    monkeypatch.setattr(httpx, "post", unreachable)

    app = _run_app()

    assert "No se pudo conectar" in app.error[0].value
    assert not app.text_area


def test_turn_form_parts_for_a_text_only_message() -> None:
    import streamlit_app

    data, files = streamlit_app.turn_form_parts(
        "Hola", ProjectType.WEB_SAAS, DetailLevel.MEDIUM, OutputFormat.NARRATIVE, uploads=[]
    )

    assert data == {
        "transcript": "Hola",
        "project_type": "web_saas",
        "detail_level": "medium",
        "output_format": "narrative",
    }
    assert files is None


def test_turn_form_parts_send_every_upload_under_the_attachments_field() -> None:
    import streamlit_app

    uploads = [
        SimpleNamespace(name="spec.pdf", type="application/pdf", getvalue=lambda: b"%PDF"),
        SimpleNamespace(name="propuesta.docx", type=None, getvalue=lambda: b"PK"),
    ]

    _, files = streamlit_app.turn_form_parts(
        "Hola", ProjectType.WEB_SAAS, DetailLevel.MEDIUM, OutputFormat.NARRATIVE, uploads
    )

    assert files == [
        ("attachments", ("spec.pdf", b"%PDF", "application/pdf")),
        ("attachments", ("propuesta.docx", b"PK", "application/octet-stream")),
    ]
