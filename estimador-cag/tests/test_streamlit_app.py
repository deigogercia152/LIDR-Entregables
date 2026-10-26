from pathlib import Path

from streamlit.testing.v1 import AppTest

from app.services import llm_services
from app.services.providers.i_llm_provider import ILLMProvider, LLMUsage

APP_PATH = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")


class FakeProvider(ILLMProvider):
    def process_message(self, system_message: str, user_message: str) -> str:
        raise AssertionError("no debería llamarse")

    def stream_message(self, system_message: str, user_message: str):
        yield "## Estimación"
        yield " de prueba"
        self.last_usage = LLMUsage(model="fake-model", input_tokens=100, output_tokens=7)


def test_chat_streams_estimation_keeps_history_and_shows_metrics(monkeypatch) -> None:
    monkeypatch.setattr(llm_services, "get_llm_provider", FakeProvider)

    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    assert not app.exception
    assert app.session_state.messages == []

    app.chat_input[0].set_value("Reunión 1: app de inventario").run()
    app.chat_input[0].set_value("Reunión 2: web corporativa").run()

    assert not app.exception
    assert [m["role"] for m in app.session_state.messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert app.session_state.messages[1]["content"] == "## Estimación de prueba"
    assert app.session_state.last_metrics["model"] == "fake-model"
    assert app.session_state.last_metrics["input_tokens"] == 100
    assert app.session_state.last_metrics["output_tokens"] == 7
    assert len(app.chat_message) == 4
    assert app.sidebar.text_area[0].value == llm_services.build_system_message()


def test_chat_shows_error_without_adding_assistant_message(monkeypatch) -> None:
    def failing_provider():
        raise ValueError("OPENAI_API_KEY no está configurada.")

    monkeypatch.setattr(llm_services, "get_llm_provider", failing_provider)

    app = AppTest.from_file(APP_PATH, default_timeout=30).run()
    app.chat_input[0].set_value("Reunión").run()

    assert not app.exception
    assert "OPENAI_API_KEY no está configurada." in app.error[0].value
    assert [m["role"] for m in app.session_state.messages] == ["user"]
