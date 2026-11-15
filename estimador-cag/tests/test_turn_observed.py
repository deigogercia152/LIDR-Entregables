import httpx
import pytest
from structlog.testing import capture_logs

from app.main import app
from app.routers import sessions as sessions_router
from app.services.llm_wrapper import ObservedProvider, compute_cost_usd
from app.services.providers.i_llm_provider import ILLMProvider, LLMUsage
from app.sessions import SessionStore

pytestmark = pytest.mark.anyio

FORM = {"project_type": "web_saas", "detail_level": "medium", "output_format": "line_items"}
TURN_OBSERVED_FIELDS = {
    "turn_index", "session_id", "enriched_transcript_chars", "attachments_total_chars",
    "messages_in_window", "anchors_count", "summary_chars", "tokens_in", "tokens_out",
    "cost_usd", "latency_ms", "cache_hit_kind", "last_resolved_tier",
}  # fmt: skip


class UsageProvider(ILLMProvider):
    """Doble que reporta uso, como los proveedores reales."""

    def process_chat(self, system_message: str, messages: list[dict[str, str]]) -> str:
        self.last_usage = LLMUsage(model="claude-haiku-5-5", input_tokens=1000, output_tokens=200)
        return "{}" if "extractor de datos" in system_message else "Estimación"

    def stream_message(self, system_message: str, user_message: str):
        raise AssertionError


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def wired(monkeypatch):
    monkeypatch.setattr(sessions_router, "session_store", SessionStore(max_sessions=10))
    monkeypatch.setattr(sessions_router, "get_llm_provider", lambda: UsageProvider())


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def _turn(client, session_id: str, transcript: str):
    return await client.post(
        f"/api/v1/sessions/{session_id}/estimate", data={**FORM, "transcript": transcript}
    )


async def test_each_turn_emits_one_turn_observed_event_with_all_fields(client) -> None:
    session_id = (await client.post("/api/v1/sessions")).json()["session_id"]

    with capture_logs() as logs:
        await _turn(client, session_id, "Una web para un club de pádel")
        await _turn(client, session_id, "Y con pagos online")

    events = [log for log in logs if log["event"] == "turn_observed"]
    assert len(events) == 2
    assert TURN_OBSERVED_FIELDS <= events[0].keys()
    assert [event["turn_index"] for event in events] == [1, 2]
    assert events[1]["messages_in_window"] == 4
    assert events[0]["session_id"] == session_id


async def test_observation_totals_cover_the_estimation_and_the_extractor_calls(client) -> None:
    session_id = (await client.post("/api/v1/sessions")).json()["session_id"]

    body = (await _turn(client, session_id, "Una web para un club de pádel")).json()

    observation = body["observation"]
    assert observation["llm_calls"] == 2
    assert observation["tokens_in"] == 2000 and observation["tokens_out"] == 400
    assert observation["cost_usd"] == pytest.approx(2 * compute_cost_usd("claude-haiku-5-5", 1000, 200))
    assert observation["attachments_total_chars"] == 0
    assert observation["cache_hit_kind"] == "none"


async def test_get_session_snapshot_exposes_memory_and_last_observation(client) -> None:
    session_id = (await client.post("/api/v1/sessions")).json()["session_id"]
    await _turn(client, session_id, "Una web para un club de pádel")

    response = await client.get(f"/api/v1/sessions/{session_id}")

    snapshot = response.json()
    assert response.status_code == 200
    assert snapshot["message_count"] == 2
    assert "club de pádel" in snapshot["window_text"]
    assert snapshot["last_observation"]["turn_index"] == 1


async def test_get_unknown_session_returns_404(client) -> None:
    assert (await client.get("/api/v1/sessions/no-existe")).status_code == 404


def test_unknown_model_costs_zero_and_known_model_uses_the_price_table() -> None:
    assert compute_cost_usd("modelo-inventado", 1000, 1000) == 0.0
    assert compute_cost_usd("claude-haiku-5-5", 1_000_000, 1_000_000) == pytest.approx(0.60)


def test_observed_provider_without_usage_reports_zero_tokens() -> None:
    class Silent(ILLMProvider):
        def process_chat(self, system_message, messages):
            return "ok"

        def stream_message(self, system_message, user_message):
            raise AssertionError

    observed = ObservedProvider(Silent())
    observed.process_chat("s", [{"role": "user", "content": "u"}])

    assert (observed.tokens_in, observed.tokens_out, observed.cost_usd) == (0, 0, 0.0)
    assert len(observed.calls) == 1 and observed.latency_ms >= 0
