"""Runner del stress test del CAG: escenarios multi-turno + adjuntos grandes -> CSV.

    uv run python -m evals.stress.run --http http://localhost:8000 \
        --scenarios growing,pivot,contradiction \
        --attachment-sizes 0,5,20,50,100 --repeats 3 \
        --output evals/stress/results.csv

Sin `--http` ejecuta la app en el mismo proceso con `TestClient` (usa el proveedor LLM
configurado en `.env`). La observación por turno viaja en la propia respuesta de
`POST /sessions/{id}/estimate` (campo `observation`) y la memoria se lee con
`GET /sessions/{id}`: así no hay que parsear logs del contenedor.
"""

import argparse
import csv
import io
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx

from evals.stress.fixtures.build_pdfs import CANARIES, build_pdf
from evals.stress.metrics import CostBudgetMetric, LatencyBudgetMetric, MemoryDriftMetric
from evals.stress.scenarios import MAX_TURNS, SCENARIOS, Scenario

API = "/api/v1"
FORM = {"project_type": "web_saas", "detail_level": "medium", "output_format": "line_items"}
ATTACHMENT_TRANSCRIPT = (
    "Estima el proyecto descrito en el documento adjunto: resume los requisitos críticos "
    "y las integraciones, y da una estimación en horas."
)
OBSERVATION_FIELDS = [
    "turn_index", "session_id", "enriched_transcript_chars", "attachments_total_chars",
    "messages_in_window", "anchors_count", "summary_chars", "tokens_in", "tokens_out",
    "cost_usd", "latency_ms", "cache_hit_kind", "last_resolved_tier", "llm_calls",
]  # fmt: skip
COLUMNS = [
    "kind", "scenario", "attachment_kb", "repeat", *OBSERVATION_FIELDS,
    "http_status", "http_latency_ms", "error", "response_chars",
    "latency_budget_ok", "cost_budget_ok",
    "facts_tracked", "facts_recalled", "recall", "recall_with_window", "stale_present",
    "recalled_facts", "canaries_total", "canaries_found", "attachment_recall",
]  # fmt: skip


def _blank_row(kind: str, scenario: str, attachment_kb: int, repeat: int) -> dict[str, Any]:
    row = dict.fromkeys(COLUMNS, "")
    row.update(kind=kind, scenario=scenario, attachment_kb=attachment_kb, repeat=repeat)
    return row


def _post_turn(
    client: httpx.Client, session_id: str, transcript: str, pdf: bytes | None = None, kb: int = 0
) -> tuple[httpx.Response, float]:
    files = {"attachments": (f"attach_{kb}kb.pdf", pdf, "application/pdf")} if pdf else None
    started = time.perf_counter()
    response = client.post(
        f"{API}/sessions/{session_id}/estimate",
        data={**FORM, "transcript": transcript},
        files=files,
    )
    return response, (time.perf_counter() - started) * 1000


def _fill_observation(row: dict[str, Any], response: httpx.Response, http_ms: float) -> bool:
    row["http_status"] = response.status_code
    row["http_latency_ms"] = round(http_ms, 1)
    if response.status_code != 200:
        row["error"] = response.text[:200].replace("\n", " ")
        return False
    body = response.json()
    row["response_chars"] = len(body["text"])
    for name in OBSERVATION_FIELDS:
        row[name] = body["observation"][name]
    return True


def score_memory(scenario: Scenario, turn_index: int, snapshot: dict[str, Any]) -> dict[str, Any]:
    """Fact-tracker del turno: ¿qué facts declarados antes siguen en la memoria?"""
    facts = scenario.facts_declared_before(turn_index)
    if not facts:
        return {"facts_tracked": 0, "recall_with_window": "", "recall": "", "stale_present": 0}
    memory = [MemoryDriftMetric(fact).evaluate(snapshot) for fact in facts]
    with_window = [MemoryDriftMetric(fact, ["summary", "anchors", "metadata", "window"]).evaluate(snapshot)
                   for fact in facts]  # fmt: skip
    stale = sum(
        MemoryDriftMetric(fact).evaluate(snapshot).passed
        for fact, superseded_at in scenario.superseded.items()
        if turn_index > superseded_at
    )
    return {
        "facts_tracked": len(facts),
        "facts_recalled": sum(r.passed for r in memory),
        "recall": round(sum(r.score for r in memory) / len(memory), 4),
        "recall_with_window": round(sum(r.score for r in with_window) / len(with_window), 4),
        "stale_present": stale,
        "recalled_facts": ";".join(r.details["fact"] for r in memory if r.passed),
    }


def run_conversation(
    client: httpx.Client, scenario: Scenario, repeat: int, max_turns: int,
    latency: LatencyBudgetMetric, cost: CostBudgetMetric,
) -> Iterator[dict[str, Any]]:  # fmt: skip
    session_id = client.post(f"{API}/sessions").json()["session_id"]
    for turn_index, transcript, _fact in scenario.turns_up_to(max_turns):
        row = _blank_row("conversation", scenario.name, 0, repeat)
        response, http_ms = _post_turn(client, session_id, transcript)
        ok = _fill_observation(row, response, http_ms)
        if ok:
            observation = response.json()["observation"]
            row["latency_budget_ok"] = int(latency.evaluate(observation).passed)
            row["cost_budget_ok"] = int(cost.evaluate(observation).passed)
            snapshot = client.get(f"{API}/sessions/{session_id}").json()
            row.update(score_memory(scenario, turn_index, snapshot))
        row["turn_index"] = turn_index
        yield row
        if not ok:
            return  # la sesión no avanzó: seguir mediría otra cosa


def run_attachment(
    client: httpx.Client, size_kb: int, repeat: int,
    latency: LatencyBudgetMetric, cost: CostBudgetMetric,
) -> dict[str, Any]:  # fmt: skip
    row = _blank_row("attachment", "attachments", size_kb, repeat)
    session_id = client.post(f"{API}/sessions").json()["session_id"]
    pdf = build_pdf(size_kb) if size_kb > 0 else None
    response, http_ms = _post_turn(client, session_id, ATTACHMENT_TRANSCRIPT, pdf, size_kb)
    if _fill_observation(row, response, http_ms):
        observation = response.json()["observation"]
        row["latency_budget_ok"] = int(latency.evaluate(observation).passed)
        row["cost_budget_ok"] = int(cost.evaluate(observation).passed)
        text = response.json()["text"].casefold()
        found = sum(canary.casefold() in text for canary in CANARIES.values())
        row["canaries_total"] = len(CANARIES) if size_kb > 0 else 0
        row["canaries_found"] = found if size_kb > 0 else ""
        row["attachment_recall"] = round(found / len(CANARIES), 4) if size_kb > 0 else ""
    return row


def build_client(http_url: str | None) -> httpx.Client:
    if http_url:
        return httpx.Client(base_url=http_url.rstrip("/"), timeout=300)
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--http", help="URL del servicio; sin ella, la app corre en el mismo proceso")
    parser.add_argument("--scenarios", default="growing,pivot,contradiction")
    parser.add_argument("--attachment-sizes", default="0,5,20,50,100", help="KB de texto; vacío = ninguno")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--max-turns", type=int, default=MAX_TURNS)
    parser.add_argument("--latency-budget-ms", type=int, default=4000)
    parser.add_argument("--cost-budget-usd", type=float, default=0.01)
    parser.add_argument("--output", type=Path, default=Path("evals/stress/results.csv"))
    args = parser.parse_args(argv)

    names = [name for name in args.scenarios.split(",") if name.strip()]
    unknown = [name for name in names if name not in SCENARIOS]
    if unknown:
        parser.error(f"escenarios desconocidos: {unknown}; disponibles: {sorted(SCENARIOS)}")
    sizes = [int(size) for size in args.attachment_sizes.split(",") if size.strip()]
    latency = LatencyBudgetMetric(args.latency_budget_ms)
    cost = CostBudgetMetric(args.cost_budget_usd)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with build_client(args.http) as client, args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()

        def emit(row: dict[str, Any]) -> None:
            nonlocal written
            writer.writerow(row)
            handle.flush()
            written += 1

        for name in names:
            for repeat in range(1, args.repeats + 1):
                print(f"[{name}] repeat {repeat}/{args.repeats}", file=sys.stderr, flush=True)
                for row in run_conversation(client, SCENARIOS[name], repeat, args.max_turns, latency, cost):
                    emit(row)
        for size in sizes:
            for repeat in range(1, args.repeats + 1):
                print(f"[attachments] {size} KB repeat {repeat}/{args.repeats}", file=sys.stderr, flush=True)
                emit(run_attachment(client, size, repeat, latency, cost))
    print(f"{written} filas -> {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
