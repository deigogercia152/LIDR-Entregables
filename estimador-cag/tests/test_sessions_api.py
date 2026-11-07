import json
import uuid

import httpx
import pytest

from app.config import settings
from app.main import app
from app.routers import sessions as sessions_router
from app.services.providers.i_llm_provider import ILLMProvider
from app.sessions import SessionStore

pytestmark = pytest.mark.anyio

FORM = {
    "project_type": "web_saas",
    "detail_level": "medium",
    "output_format": "line_items",
}


class ScriptedProvider(ILLMProvider):
    """Doble del LLM: distingue la llamada del extractor de la de estimación."""

    def __init__(self, extractor_replies: list[str] | None = None) -> None:
        self.estimation_calls: list[tuple[str, list[dict[str, str]]]] = []
        self.extraction_calls: list[tuple[str, list[dict[str, str]]]] = []
        self._extractor_replies = list(extractor_replies or [])

    def process_chat(self, system_message: str, messages: list[dict[str, str]]) -> str:
        if "extractor de datos" in system_message:
            self.extraction_calls.append((system_message, messages))
            return self._extractor_replies.pop(0) if self._extractor_replies else "{}"
        self.estimation_calls.append((system_message, messages))
        reply = f"Estimación {len(self.estimation_calls)}"
        # La salida depende de lo que recibe: así se ve que un adjunto la cambia.
        if "KAFKA-9731" in messages[-1]["content"]:
            reply += " | incluye mensajería Kafka"
        return reply

    def stream_message(self, system_message: str, user_message: str):
        raise AssertionError("las sesiones no usan streaming")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def fresh_store(monkeypatch) -> SessionStore:
    store = SessionStore(max_sessions=50)
    monkeypatch.setattr(sessions_router, "session_store", store)
    return store


@pytest.fixture
def provider(monkeypatch) -> ScriptedProvider:
    scripted = ScriptedProvider()
    monkeypatch.setattr(sessions_router, "get_llm_provider", lambda: scripted)
    return scripted


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def new_session(client: httpx.AsyncClient) -> str:
    response = await client.post("/api/v1/sessions")
    assert response.status_code == 201
    return response.json()["session_id"]


async def estimate(client, session_id: str, transcript: str, files=None, **overrides):
    return await client.post(
        f"/api/v1/sessions/{session_id}/estimate",
        data={**FORM, "transcript": transcript, **overrides},
        files=files,
    )


async def test_create_session_returns_distinct_uuid4_ids(client) -> None:
    first, second = await new_session(client), await new_session(client)

    assert first != second
    assert uuid.UUID(first).version == 4


async def test_estimate_on_an_unknown_session_returns_404(client, provider) -> None:
    response = await estimate(client, "no-existe", "Una web para un club de pádel")

    assert response.status_code == 404
    assert provider.estimation_calls == []


async def test_metadata_is_updated_and_reinjected_across_two_requests(client, monkeypatch) -> None:
    scripted = ScriptedProvider(
        extractor_replies=[
            json.dumps(
                {
                    "project_name": "Club Pádel",
                    "assumed_team_size": 2,
                    "mentioned_technologies": ["Django"],
                    "agreed_scope": "Web de reservas de pistas",
                }
            ),
            # Respuesta con texto alrededor: el extractor es un LLM y no siempre es limpio.
            'Claro: {"assumed_team_size": 3, "mentioned_technologies": ["django", "Redis"],'
            ' "agreed_scope": "Web de reservas y app móvil"}',
        ]
    )
    monkeypatch.setattr(sessions_router, "get_llm_provider", lambda: scripted)
    session_id = await new_session(client)

    first = await estimate(client, session_id, "Web de reservas para el Club Pádel con Django")
    second = await estimate(client, session_id, "Añadid también una app móvil")

    assert first.status_code == second.status_code == 200
    assert first.json()["project_metadata"] == {
        "project_name": "Club Pádel",
        "assumed_team_size": 2,
        "mentioned_technologies": ["Django"],
        "agreed_scope": "Web de reservas de pistas",
    }
    assert second.json()["project_metadata"] == {
        "project_name": "Club Pádel",  # el segundo update no lo trae: se conserva
        "assumed_team_size": 3,
        "mentioned_technologies": ["Django", "Redis"],
        "agreed_scope": "Web de reservas y app móvil",
    }
    assert [first.json()["turn"], second.json()["turn"]] == [1, 2]
    first_system, first_messages = scripted.estimation_calls[0]
    second_system, second_messages = scripted.estimation_calls[1]
    assert "Nombre del proyecto" not in first_system  # primera llamada: bloque vacío
    assert "Nombre del proyecto: Club Pádel" in second_system
    assert "Tecnologías mencionadas: Django" in second_system
    assert [m["role"] for m in second_messages] == ["user", "assistant", "user"]
    assert second_messages[1]["content"] == "Estimación 1"
    # El extractor ve los hechos ya conocidos para poder actualizarlos.
    assert "Club Pádel" in scripted.extraction_calls[1][1][0]["content"]


async def test_a_pdf_attachment_changes_the_estimation_and_reaches_the_prompt(
    client, provider, make_pdf
) -> None:
    transcript = "Necesitamos un sistema de avisos para los socios"
    without_attachment = await estimate(client, await new_session(client), transcript)
    pdf = make_pdf("La arquitectura usara KAFKA-9731 para los eventos")

    with_attachment = await estimate(
        client,
        await new_session(client),
        transcript,
        files=[("attachments", ("spec.pdf", pdf, "application/pdf"))],
    )

    assert "Kafka" not in without_attachment.json()["text"]
    assert "incluye mensajería Kafka" in with_attachment.json()["text"]
    user_message = provider.estimation_calls[-1][1][-1]["content"]
    assert "--- attachment: spec.pdf ---" in user_message
    assert "KAFKA-9731" in user_message
    assert user_message.index(transcript) < user_message.index("spec.pdf")


async def test_docx_and_pdf_can_be_attached_together(client, provider, make_pdf, make_docx) -> None:
    files = [
        ("attachments", ("spec.pdf", make_pdf("texto del pdf"), "application/pdf")),
        ("attachments", ("propuesta.docx", make_docx("texto del word"), "application/octet-stream")),
    ]

    response = await estimate(client, await new_session(client), "Revisad los documentos", files)

    assert response.status_code == 200
    user_message = provider.estimation_calls[0][1][-1]["content"]
    assert "--- attachment: spec.pdf ---\ntexto del pdf" in user_message
    assert "--- attachment: propuesta.docx ---\ntexto del word" in user_message


async def test_a_rejected_attachment_does_not_touch_the_session(client, provider) -> None:
    session_id = await new_session(client)

    rejected = await estimate(
        client,
        session_id,
        "Mirad este fichero",
        files=[("attachments", ("notas.txt", b"hola", "text/plain"))],
    )
    accepted = await estimate(client, session_id, "Una web para un club de pádel")

    assert rejected.status_code == 415
    assert "formato no soportado" in rejected.json()["detail"]
    assert accepted.json()["turn"] == 1
    assert len(provider.estimation_calls) == 1  # el rechazado nunca llegó al LLM
    assert len(provider.estimation_calls[0][1]) == 1  # y no dejó nada en el historial


async def test_estimate_works_without_attachments_field(client, provider) -> None:
    response = await estimate(client, await new_session(client), "Una web para un club de pádel")

    assert response.status_code == 200
    assert response.json()["prompt_version"] == "v1"
    assert "--- attachment" not in provider.estimation_calls[0][1][0]["content"]


@pytest.mark.parametrize(
    "form",
    [
        {"transcript": "   "},
        {"transcript": "x" * 20_001},
        {"transcript": "ok", "project_type": "MOBILE_APP"},
        {"transcript": "ok", "detail_level": "extreme"},
    ],
)
async def test_invalid_forms_are_rejected_with_422(client, provider, form: dict) -> None:
    session_id = await new_session(client)

    response = await client.post(
        f"/api/v1/sessions/{session_id}/estimate", data={**FORM, **form}
    )

    assert response.status_code == 422
    assert provider.estimation_calls == []


async def test_short_follow_up_messages_are_accepted(client, provider) -> None:
    response = await estimate(client, await new_session(client), "¿Y con app móvil?")

    assert response.status_code == 200


async def test_history_sent_to_the_llm_never_exceeds_the_sliding_window(
    client, provider, monkeypatch
) -> None:
    """Ventana de 3 turnos completos: el LLM recibe como máximo 3 pares + el mensaje nuevo."""
    monkeypatch.setattr(settings, "session_max_turns", 3)
    session_id = await new_session(client)

    reported_turns = []
    for turn in range(1, 9):
        response = await estimate(client, session_id, f"pregunta {turn}")
        assert response.status_code == 200
        reported_turns.append(response.json()["turn"])

    # `turn` cuenta los turnos de la sesión, no los que caben en la ventana.
    assert reported_turns == list(range(1, 9))
    assert len(provider.estimation_calls) == 8
    for turn, (system, messages) in enumerate(provider.estimation_calls, start=1):
        previous_pairs = min(turn - 1, 3)
        assert len(messages) == 2 * previous_pairs + 1, f"turno {turn}"
        assert [m["role"] for m in messages] == ["user", "assistant"] * previous_pairs + ["user"]
        assert f"pregunta {turn}" in messages[-1]["content"]
        assert isinstance(system, str) and system  # el system prompt va siempre
    _, last_messages = provider.estimation_calls[7]
    kept_questions = [m["content"] for m in last_messages if m["role"] == "user"]
    assert [f"pregunta {n}" in kept_questions[i] for i, n in enumerate((5, 6, 7, 8))] == [True] * 4
    assert not any("pregunta 4" in content for content in kept_questions)  # el más antiguo cae


async def test_a_garbage_extractor_reply_keeps_the_estimation_and_the_old_metadata(
    client, monkeypatch
) -> None:
    scripted = ScriptedProvider(
        extractor_replies=['{"project_name": "Club Pádel"}', "esto no es JSON", '{"assumed_team_size": 0}']
    )
    monkeypatch.setattr(sessions_router, "get_llm_provider", lambda: scripted)
    session_id = await new_session(client)

    await estimate(client, session_id, "Primer mensaje")
    garbage = await estimate(client, session_id, "Segundo mensaje")
    invalid = await estimate(client, session_id, "Tercer mensaje")

    for response in (garbage, invalid):
        assert response.status_code == 200
        assert response.json()["project_metadata"]["project_name"] == "Club Pádel"
        assert response.json()["project_metadata"]["assumed_team_size"] is None


async def test_the_session_survives_an_llm_failure_without_recording_the_turn(
    monkeypatch, provider
) -> None:
    calls = {"count": 0}
    original = provider.process_chat

    def flaky(system_message: str, messages: list[dict[str, str]]) -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("proveedor caído")
        return original(system_message, messages)

    monkeypatch.setattr(provider, "process_chat", flaky)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        session_id = await new_session(client)

        failed = await estimate(client, session_id, "Primer intento")
        retried = await estimate(client, session_id, "Segundo intento")

    assert failed.status_code == 500
    assert retried.status_code == 200
    assert retried.json()["turn"] == 1
    assert len(provider.estimation_calls[0][1]) == 1  # el turno fallido no quedó en el historial


async def test_estimate_returns_503_when_the_provider_is_not_configured(
    client, monkeypatch
) -> None:
    def missing_key():
        raise ValueError("OPENAI_API_KEY no está configurada.")

    monkeypatch.setattr(sessions_router, "get_llm_provider", missing_key)

    response = await estimate(client, await new_session(client), "Una web para un club de pádel")

    assert response.status_code == 503
    assert response.json() == {"detail": "OPENAI_API_KEY no está configurada."}
