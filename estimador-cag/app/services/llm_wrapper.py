"""Envoltorio observable de un proveedor LLM: latencia, tokens y coste por llamada.

No cambia el comportamiento del proveedor; solo mide. Un turno de sesión hace varias
llamadas (estimación + extractor de metadata), así que el wrapper acumula las
llamadas y expone los totales del turno.
"""

import time
from collections.abc import Iterator
from dataclasses import dataclass

import structlog

from app.services.providers.i_llm_provider import ILLMProvider, LLMUsage

logger = structlog.get_logger(__name__)

# USD por millón de tokens (entrada, salida). Tarifas de lista de la API de Anthropic y
# OpenAI; un modelo que no esté aquí se contabiliza a 0 USD y se avisa en el log.
MODEL_COSTS: dict[str, tuple[float, float]] = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-fable-5-1": (10.00, 50.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}


def compute_cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    prices = MODEL_COSTS.get(model)
    if prices is None:
        logger.warning("model_cost_unknown", model=model)
        return 0.0
    return (tokens_in * prices[0] + tokens_out * prices[1]) / 1_000_000


@dataclass(frozen=True)
class LLMCall:
    model: str
    latency_ms: float
    tokens_in: int
    tokens_out: int
    cost_usd: float


class ObservedProvider(ILLMProvider):
    """Delega en `inner` y registra una `LLMCall` por cada `process_chat`."""

    def __init__(self, inner: ILLMProvider) -> None:
        self._inner = inner
        self.calls: list[LLMCall] = []

    def process_chat(self, system_message: str, messages: list[dict[str, str]]) -> str:
        started = time.perf_counter()
        text = self._inner.process_chat(system_message, messages)
        latency_ms = (time.perf_counter() - started) * 1000
        usage: LLMUsage | None = self._inner.last_usage
        tokens_in = usage.input_tokens if usage else 0
        tokens_out = usage.output_tokens if usage else 0
        model = usage.model if usage else ""
        self.last_usage = usage
        self.calls.append(
            LLMCall(model, latency_ms, tokens_in, tokens_out, compute_cost_usd(model, tokens_in, tokens_out))
        )
        return text

    def stream_message(self, system_message: str, user_message: str) -> Iterator[str]:
        return self._inner.stream_message(system_message, user_message)

    @property
    def tokens_in(self) -> int:
        return sum(call.tokens_in for call in self.calls)

    @property
    def tokens_out(self) -> int:
        return sum(call.tokens_out for call in self.calls)

    @property
    def cost_usd(self) -> float:
        return sum(call.cost_usd for call in self.calls)

    @property
    def latency_ms(self) -> float:
        return sum(call.latency_ms for call in self.calls)
