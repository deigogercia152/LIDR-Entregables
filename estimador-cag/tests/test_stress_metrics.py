import pytest

from evals.stress.metrics import (
    CostBudgetMetric,
    LatencyBudgetMetric,
    MemoryDriftMetric,
)

SNAPSHOT = {
    "summary": "El cliente quiere una app llamada Nimbus.",
    "anchors": ["budget locked: 30000 EUR"],
    "project_metadata": {
        "project_name": "Nimbus",
        "assumed_team_size": 4,
        "mentioned_technologies": ["Flutter", "Django"],
        "agreed_scope": "Panel con audit log",
    },
    "window_text": "turno reciente con multi-tenant",
}


def test_latency_budget_passes_under_budget_and_fails_over() -> None:
    metric = LatencyBudgetMetric(budget_ms=4000)

    assert metric.evaluate({"latency_ms": 3999.0}).passed
    result = metric.evaluate({"latency_ms": 4000.1})
    assert (result.score, result.passed) == (0.0, False)
    assert result.details["budget_ms"] == 4000


def test_latency_and_cost_budgets_pass_exactly_at_the_limit() -> None:
    assert LatencyBudgetMetric(4000).evaluate({"latency_ms": 4000}).passed
    assert CostBudgetMetric(0.01).evaluate({"cost_usd": 0.01}).passed


def test_cost_budget_fails_over_budget_and_when_the_field_is_missing() -> None:
    metric = CostBudgetMetric(budget_usd=0.01)

    assert metric.evaluate({"cost_usd": 0.0099}).score == 1.0
    assert metric.evaluate({"cost_usd": 0.02}).passed is False
    assert metric.evaluate({}).passed is False


def test_memory_drift_finds_the_fact_case_insensitively_in_the_requested_places() -> None:
    result = MemoryDriftMetric("nimbus").evaluate(SNAPSHOT)

    assert result.passed and result.score == 1.0
    assert set(result.details["found_in"]) == {"summary", "metadata"}


def test_memory_drift_fails_when_the_fact_is_only_in_the_window_by_default() -> None:
    assert MemoryDriftMetric("multi-tenant").evaluate(SNAPSHOT).passed is False
    assert MemoryDriftMetric("multi-tenant", where=["window"]).evaluate(SNAPSHOT).passed


def test_memory_drift_finds_anchors_and_technologies_and_rejects_an_empty_fact() -> None:
    assert MemoryDriftMetric("30000 EUR", where=["anchors"]).evaluate(SNAPSHOT).passed
    assert MemoryDriftMetric("flutter", where=["metadata"]).evaluate(SNAPSHOT).passed
    assert MemoryDriftMetric("").evaluate(SNAPSHOT).passed is False
    assert MemoryDriftMetric("anything").evaluate({}).passed is False


def test_memory_drift_rejects_an_unknown_location() -> None:
    with pytest.raises(ValueError):
        MemoryDriftMetric("x", where=["nowhere"]).evaluate(SNAPSHOT)
