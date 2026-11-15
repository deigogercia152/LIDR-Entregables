"""Agrega results.csv en las tablas del REPORT.md (Markdown puro, sin gráficos).

    uv run python -m evals.stress.report evals/stress/results.csv
"""

import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from evals.stress.scenarios import CHECKPOINTS


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    rank = (len(ordered) - 1) * pct
    low, high = int(rank), min(int(rank) + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def _f(row: dict[str, str], key: str) -> float | None:
    return float(row[key]) if row.get(key) not in ("", None) else None


def _mean(values: list[float]) -> str:
    return f"{statistics.mean(values):.2f}" if values else "–"


def load(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def summary_table(rows: list[dict[str, str]]) -> str:
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[(row["scenario"], row["attachment_kb"])].append(row)
    lines = [
        "| escenario | adjunto KB | filas | errores HTTP | P50 latency ms | P95 latency ms | coste total USD "
        "| coste medio/turno USD | exact hit | semantic hit | recall medio (memoria) | recall medio (+ventana) | "
        "recall adjunto |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for (scenario, kb), group in sorted(groups.items(), key=lambda item: (item[0][0], int(item[0][1]))):
        ok = [r for r in group if r["http_status"] == "200"]
        latencies = [float(r["latency_ms"]) for r in ok]
        costs = [float(r["cost_usd"]) for r in ok]
        exact = sum(r["cache_hit_kind"] == "exact" for r in ok) / len(ok) if ok else 0
        semantic = sum(r["cache_hit_kind"] == "semantic" for r in ok) / len(ok) if ok else 0
        recall = [v for r in ok if (v := _f(r, "recall")) is not None]
        recall_w = [v for r in ok if (v := _f(r, "recall_with_window")) is not None]
        attach = [v for r in ok if (v := _f(r, "attachment_recall")) is not None]
        errors = len(group) - len(ok)
        lines.append(
            f"| {scenario} | {kb} | {len(group)} | {errors} | "
            f"{percentile(latencies, 0.5):.0f} | {percentile(latencies, 0.95):.0f} | {sum(costs):.4f} | "
            f"{_mean(costs) if not costs else f'{statistics.mean(costs):.5f}'} | {exact:.0%} | {semantic:.0%} | "
            f"{_mean(recall)} | {_mean(recall_w)} | {_mean(attach)} |"
        )
    return "\n".join(lines)


def curve_latency_vs_tokens(rows: list[dict[str, str]]) -> str:
    ok = [r for r in rows if r["http_status"] == "200"]
    edges = [0, 3000, 6000, 10000, 15000, 25000, 10**9]
    lines = ["| tokens_in (rango) | n | latency ms medio | P95 ms | tokens_out medio | coste medio USD |",
             "|---|---|---|---|---|---|"]  # fmt: skip
    for low, high in zip(edges, edges[1:]):
        bucket = [r for r in ok if low <= float(r["tokens_in"]) < high]
        if not bucket:
            continue
        lat = [float(r["latency_ms"]) for r in bucket]
        label = f"{low}–{high}" if high < 10**9 else f"≥{low}"
        lines.append(
            f"| {label} | {len(bucket)} | {statistics.mean(lat):.0f} | {percentile(lat, 0.95):.0f} | "
            f"{statistics.mean(float(r['tokens_out']) for r in bucket):.0f} | "
            f"{statistics.mean(float(r['cost_usd']) for r in bucket):.5f} |"
        )
    return "\n".join(lines)


def curve_cumulative_cost(rows: list[dict[str, str]]) -> str:
    conv = [r for r in rows if r["kind"] == "conversation" and r["http_status"] == "200"]
    lines = ["| turno N | " + " | ".join(sorted({r["scenario"] for r in conv})) + " |",
             "|---|" + "---|" * len({r["scenario"] for r in conv})]  # fmt: skip
    scenarios = sorted({r["scenario"] for r in conv})
    cumulative: dict[tuple[str, str], dict[int, float]] = defaultdict(dict)
    for scenario in scenarios:
        by_repeat: dict[str, list[dict[str, str]]] = defaultdict(list)
        for r in conv:
            if r["scenario"] == scenario:
                by_repeat[r["repeat"]].append(r)
        for repeat, turns in by_repeat.items():
            running = 0.0
            for r in sorted(turns, key=lambda r: int(r["turn_index"])):
                running += float(r["cost_usd"])
                cumulative[(scenario, repeat)][int(r["turn_index"])] = running
    for n in CHECKPOINTS:
        cells = []
        for scenario in scenarios:
            vals = [turns[n] for (s, _), turns in cumulative.items() if s == scenario and n in turns]
            cells.append(f"{statistics.mean(vals):.4f}" if vals else "–")
        lines.append(f"| {n} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def curve_per_turn_cost(rows: list[dict[str, str]]) -> str:
    conv = [r for r in rows if r["kind"] == "conversation" and r["http_status"] == "200"]
    scenarios = sorted({r["scenario"] for r in conv})
    lines = ["| turno N | " + " | ".join(f"{s} tokens_in / ms" for s in scenarios) + " |",
             "|---|" + "---|" * len(scenarios)]  # fmt: skip
    for n in CHECKPOINTS:
        cells = []
        for scenario in scenarios:
            sel = [r for r in conv if r["scenario"] == scenario and int(r["turn_index"]) == n]
            cells.append(
                f"{statistics.mean(float(r['tokens_in']) for r in sel):.0f} / "
                f"{statistics.mean(float(r['latency_ms']) for r in sel):.0f}" if sel else "–"
            )
        lines.append(f"| {n} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def curve_recall_vs_n(rows: list[dict[str, str]]) -> str:
    conv = [r for r in rows if r["kind"] == "conversation" and r["http_status"] == "200" and r["recall"] != ""]
    scenarios = sorted({r["scenario"] for r in conv})
    header = " | ".join(f"{s} memoria / +ventana" for s in scenarios)
    lines = [f"| turno N | {header} |", "|---|" + "---|" * len(scenarios)]
    for n in CHECKPOINTS:
        cells = []
        for scenario in scenarios:
            sel = [r for r in conv if r["scenario"] == scenario and int(r["turn_index"]) == n]
            cells.append(
                f"{statistics.mean(float(r['recall']) for r in sel):.2f} / "
                f"{statistics.mean(float(r['recall_with_window']) for r in sel):.2f}" if sel else "–"
            )
        lines.append(f"| {n} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def curve_attachment(rows: list[dict[str, str]]) -> str:
    att = [r for r in rows if r["kind"] == "attachment"]
    lines = ["| adjunto KB | HTTP | chars extraídos | tokens_in | latency ms | coste USD | recall canarios |",
             "|---|---|---|---|---|---|---|"]  # fmt: skip
    for kb in sorted({int(r["attachment_kb"]) for r in att}):
        sel = [r for r in att if int(r["attachment_kb"]) == kb]
        ok = [r for r in sel if r["http_status"] == "200"]
        statuses = ",".join(sorted({r["http_status"] for r in sel}))
        if not ok:
            lines.append(f"| {kb} | {statuses} | – | – | – | – | – |")
            continue
        recall = [v for r in ok if (v := _f(r, "attachment_recall")) is not None]
        lines.append(
            f"| {kb} | {statuses} | {statistics.mean(float(r['attachments_total_chars']) for r in ok):.0f} | "
            f"{statistics.mean(float(r['tokens_in']) for r in ok):.0f} | "
            f"{statistics.mean(float(r['latency_ms']) for r in ok):.0f} | "
            f"{statistics.mean(float(r['cost_usd']) for r in ok):.5f} | {_mean(recall)} |"
        )
    return "\n".join(lines)


def main(path: str) -> None:
    rows = load(Path(path))
    sections = [
        ("Resumen", summary_table(rows)),
        ("Curva 1 — latencia vs tokens_in", curve_latency_vs_tokens(rows)),
        ("Curva 1b — tokens_in y latencia por turno", curve_per_turn_cost(rows)),
        ("Curva 2 — coste acumulado (USD) vs turno", curve_cumulative_cost(rows)),
        ("Curva 3 — recall del fact-tracker vs turno", curve_recall_vs_n(rows)),
        ("Escenario de adjuntos", curve_attachment(rows)),
    ]
    for title, table in sections:
        print(f"### {title}\n\n{table}\n")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "evals/stress/results.csv")
