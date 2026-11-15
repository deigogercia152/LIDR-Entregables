import csv

import pytest

from app.routers import sessions as sessions_router
from app.services.providers.i_llm_provider import ILLMProvider, LLMUsage
from app.sessions import SessionStore
from evals.stress import run as stress_run


class EchoProvider(ILLMProvider):
    """Estimación = eco del mensaje (así los canarios del adjunto 'sobreviven'); extractor = JSON fijo."""

    def process_chat(self, system_message: str, messages: list[dict[str, str]]) -> str:
        self.last_usage = LLMUsage(model="claude-haiku-5-5", input_tokens=500, output_tokens=100)
        if "extractor de datos" in system_message:
            return '{"project_name": "Nimbus", "mentioned_technologies": ["React"]}'
        return messages[-1]["content"]

    def stream_message(self, system_message: str, user_message: str):
        raise AssertionError


@pytest.fixture(autouse=True)
def wired(monkeypatch):
    monkeypatch.setattr(sessions_router, "session_store", SessionStore(max_sessions=50))
    monkeypatch.setattr(sessions_router, "get_llm_provider", lambda: EchoProvider())


def _run(tmp_path, *extra: str) -> list[dict[str, str]]:
    output = tmp_path / "out.csv"
    assert stress_run.main(["--output", str(output), *extra]) == 0
    with output.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_conversation_rows_carry_the_observation_and_the_memory_scores(tmp_path) -> None:
    rows = _run(tmp_path, "--scenarios", "pivot", "--attachment-sizes", "", "--repeats", "1", "--max-turns", "6")

    assert [row["turn_index"] for row in rows] == ["1", "2", "3", "4", "5", "6"]
    assert set(stress_run.COLUMNS) == set(rows[0])
    assert rows[0]["facts_tracked"] == "0" and rows[1]["facts_tracked"] == "1"
    assert rows[1]["recall"] == "1.0"  # "React" está en la metadata del extractor
    assert rows[5]["stale_present"] == "1"  # React sigue en la memoria tras el pivot del turno 5
    assert int(rows[0]["tokens_in"]) == 1000 and rows[0]["latency_budget_ok"] == "1"


def test_attachment_rows_measure_canary_recall_and_the_hard_cap(tmp_path) -> None:
    rows = _run(tmp_path, "--scenarios", "", "--attachment-sizes", "0,5,100", "--repeats", "1")

    by_kb = {row["attachment_kb"]: row for row in rows}
    assert by_kb["0"]["attachment_recall"] == "" and by_kb["0"]["http_status"] == "200"
    assert by_kb["5"]["attachment_recall"] == "1.0" and int(by_kb["5"]["attachments_total_chars"]) > 5000
    assert by_kb["100"]["http_status"] == "413" and "demasiado texto" in by_kb["100"]["error"]


def test_unknown_scenario_is_rejected(tmp_path) -> None:
    with pytest.raises(SystemExit):
        stress_run.main(["--scenarios", "nope", "--output", str(tmp_path / "x.csv")])
