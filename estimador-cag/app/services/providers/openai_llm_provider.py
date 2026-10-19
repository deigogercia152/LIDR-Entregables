from openai import OpenAI

from .i_llm_provider import ILLMProvider


class OpenAILLMProvider(ILLMProvider):
	def __init__(
		self,
		api_key: str,
		model: str,
		max_tokens: int = 2048,
	) -> None:
		self.client = OpenAI(api_key=api_key)
		self.model = model
		self.max_tokens = max_tokens

	def process_message(self, system_message: str, user_message: str) -> str:
		response = self.client.chat.completions.create(
			model=self.model,
			max_tokens=self.max_tokens,
			messages=[
				{"role": "system", "content": system_message},
				{"role": "user", "content": user_message},
			],
		)
		if not response.choices or response.choices[0].message.content is None:
			raise RuntimeError("OpenAI devolvió una respuesta sin contenido de texto.")
		return response.choices[0].message.content