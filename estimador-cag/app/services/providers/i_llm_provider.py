from abc import ABC, abstractmethod


class ILLMProvider(ABC):
	"""Interfaz para proveedores de modelos de lenguaje."""

	@abstractmethod
	def process_message(self, system_message: str, user_message: str) -> str:
		"""Envía las instrucciones del sistema y el mensaje del usuario al modelo."""
		raise NotImplementedError
