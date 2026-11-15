import pytest

from evals.stress.report import percentile, summary_table


def test_percentile_interpolates_and_handles_edges() -> None:
    assert percentile([10.0], 0.95) == 10.0
    assert percentile([0.0, 100.0], 0.5) == 50.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.95) == pytest.approx(3.85)


def test_summary_table_counts_http_errors_separately() -> None:
    base = dict.fromkeys(
        ["recall", "recall_with_window", "attachment_recall", "latency_ms", "cost_usd", "cache_hit_kind"], ""
    )
    ok = {**base, "scenario": "attachments", "attachment_kb": "5", "http_status": "200",
          "latency_ms": "1000", "cost_usd": "0.002", "cache_hit_kind": "none", "attachment_recall": "1.0"}  # fmt: skip
    bad = {**base, "scenario": "attachments", "attachment_kb": "5", "http_status": "413"}

    table = summary_table([ok, bad])

    assert "| attachments | 5 | 2 | 1 | 1000 | 1000 | 0.0020 |" in table
