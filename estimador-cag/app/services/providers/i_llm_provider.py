from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMUsage:
	"""Métricas de consumo de la última llamada al modelo."""

	model: str
	input_tokens: int
	output_tokens: int


class ILLMProvider(ABC):
	"""Interfaz para proveedores de modelos de lenguaje."""

	last_usage: LLMUsage | None = None

	@abstractmethod
	def process_message(self, system_message: str, user_message: str) -> str:
		"""Envía las instrucciones del sistema y el mensaje del usuario al modelo."""
		raise NotImplementedError

	@abstractmethod
	def stream_message(self, system_message: str, user_message: str) -> Iterator[str]:
		"""Igual que process_message, pero devuelve el texto en fragmentos según llega.

		Al agotar el iterador, `last_usage` contiene las métricas de la llamada.
		"""
		raise NotImplementedError
