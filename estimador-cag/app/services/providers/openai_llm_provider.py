from collections.abc import Iterator

from openai import OpenAI

from .i_llm_provider import ILLMProvider, LLMUsage


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

	def stream_message(self, system_message: str, user_message: str) -> Iterator[str]:
		self.last_usage = None
		stream = self.client.chat.completions.create(
			model=self.model,
			max_tokens=self.max_tokens,
			messages=[
				{"role": "system", "content": system_message},
				{"role": "user", "content": user_message},
			],
			stream=True,
			stream_options={"include_usage": True},
		)
		for chunk in stream:
			if chunk.choices and chunk.choices[0].delta.content:
				yield chunk.choices[0].delta.content
			if chunk.usage:
				self.last_usage = LLMUsage(
					model=self.model,
					input_tokens=chunk.usage.prompt_tokens,
					output_tokens=chunk.usage.completion_tokens,
				)
