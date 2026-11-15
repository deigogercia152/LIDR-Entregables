"""Métricas deterministas del stress test del CAG.

Viven aquí y no en un `evals/metrics.py` general porque dependen del shape de
`turn_observed` (latencia, coste) y del snapshot de sesión (memoria), no de una
estimación. Mismo patrón `MetricResult(name, score, passed, details)`.
Determinismo > sofisticación: sin embeddings ni LLM-as-judge, solo coincidencia
exacta sin distinguir mayúsculas.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

MEMORY_LOCATIONS = ("summary", "anchors", "metadata")


@dataclass(frozen=True)
class MetricResult:
    name: str
    score: float
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)


def _value(observation: Any, key: str) -> Any:
    if isinstance(observation, Mapping):
        return observation.get(key)
    return getattr(observation, key, None)


class LatencyBudgetMetric:
    """1.0 si latency_ms <= budget_ms; 0.0 si no (el límite exacto cumple)."""

    name = "latency_budget"

    def __init__(self, budget_ms: int) -> None:
        self.budget_ms = budget_ms

    def evaluate(self, observation: Any) -> MetricResult:
        latency = _value(observation, "latency_ms")
        passed = latency is not None and latency <= self.budget_ms
        return MetricResult(
            self.name, 1.0 if passed else 0.0, passed,
            {"latency_ms": latency, "budget_ms": self.budget_ms},
        )  # fmt: skip


class CostBudgetMetric:
    """1.0 si cost_usd <= budget_usd; 0.0 si no (el límite exacto cumple)."""

    name = "cost_budget"

    def __init__(self, budget_usd: float) -> None:
        self.budget_usd = budget_usd

    def evaluate(self, observation: Any) -> MetricResult:
        cost = _value(observation, "cost_usd")
        passed = cost is not None and cost <= self.budget_usd
        return MetricResult(
            self.name, 1.0 if passed else 0.0, passed,
            {"cost_usd": cost, "budget_usd": self.budget_usd},
        )  # fmt: skip


class MemoryDriftMetric:
    """1.0 si `fact` aparece en alguno de los campos de memoria del snapshot.

    `where` elige dónde buscar: "summary", "anchors", "metadata" (los tres del
    enunciado) y, opcionalmente, "window" (los mensajes aún dentro de la ventana
    deslizante). El llamador solo debe evaluarla en un turno N posterior al k que
    declaró el fact.
    """

    name = "memory_drift"

    def __init__(self, fact: str, where: list[str] | None = None) -> None:
        self.fact = fact
        self.where = list(where) if where is not None else list(MEMORY_LOCATIONS)

    def evaluate(self, session_snapshot: Mapping[str, Any]) -> MetricResult:
        needle = self.fact.casefold()
        found_in = [
            place for place in self.where if needle and needle in self._haystack(session_snapshot, place)
        ]
        return MetricResult(
            self.name, 1.0 if found_in else 0.0, bool(found_in),
            {"fact": self.fact, "found_in": found_in, "searched": self.where},
        )  # fmt: skip

    @staticmethod
    def _haystack(snapshot: Mapping[str, Any], place: str) -> str:
        if place == "summary":
            text = snapshot.get("summary") or ""
        elif place == "anchors":
            text = "\n".join(snapshot.get("anchors") or [])
        elif place == "metadata":
            meta = snapshot.get("project_metadata") or {}
            text = "\n".join(
                [
                    str(meta.get("project_name") or ""),
                    str(meta.get("assumed_team_size") or ""),
                    "\n".join(meta.get("mentioned_technologies") or []),
                    str(meta.get("agreed_scope") or ""),
                ]
            )
        elif place == "window":
            text = snapshot.get("window_text") or ""
        else:
            raise ValueError(f"ubicación de memoria desconocida: {place}")
        return text.casefold()
