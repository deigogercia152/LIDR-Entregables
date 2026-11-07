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
	def process_chat(self, system_message: str, messages: list[dict[str, str]]) -> str:
		"""Envía las instrucciones del sistema y una conversación al modelo.

		`messages` es el array de turnos `{"role": "user" | "assistant", "content": ...}`
		sin el mensaje de sistema, que viaja aparte porque Anthropic lo exige así.
		"""
		raise NotImplementedError

	def process_message(self, system_message: str, user_message: str) -> str:
		"""Envía las instrucciones del sistema y un único mensaje del usuario al modelo."""
		return self.process_chat(system_message, [{"role": "user", "content": user_message}])

	@abstractmethod
	def stream_message(self, system_message: str, user_message: str) -> Iterator[str]:
		"""Igual que process_message, pero devuelve el texto en fragmentos según llega.

		Al agotar el iterador, `last_usage` contiene las métricas de la llamada.
		"""
		raise NotImplementedError
