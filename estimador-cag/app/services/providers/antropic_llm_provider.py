from anthropic import Anthropic

from .i_llm_provider import ILLMProvider


class AnthropicLLMProvider(ILLMProvider):
	def __init__(
		self,
		api_key: str,
		model: str,
		max_tokens: int = 2048,
	) -> None:
		self.client = Anthropic(api_key=api_key)
		self.model = model
		self.max_tokens = max_tokens

	def process_message(self, system_message: str, user_message: str) -> str:
		response = self.client.messages.create(
			model=self.model,
			max_tokens=self.max_tokens,
			system=system_message,
			messages=[{"role": "user", "content": user_message}],
		)
		text = "".join(
			block.text for block in response.content if getattr(block, "type", None) == "text"
		)
		if not text:
			raise RuntimeError("Anthropic devolvió una respuesta sin contenido de texto.")
		return text
