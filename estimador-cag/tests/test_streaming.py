from types import SimpleNamespace

from app.services.providers.antropic_llm_provider import AnthropicLLMProvider
from app.services.providers.i_llm_provider import LLMUsage
from app.services.providers.openai_llm_provider import OpenAILLMProvider


def _openai_chunk(content: str | None = None, usage=None) -> SimpleNamespace:
    choices = [] if content is None else [SimpleNamespace(delta=SimpleNamespace(content=content))]
    return SimpleNamespace(choices=choices, usage=usage)


def test_openai_stream_yields_text_and_records_usage() -> None:
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return iter(
            [
                _openai_chunk("Hola"),
                _openai_chunk(" mundo"),
                _openai_chunk(None, SimpleNamespace(prompt_tokens=12, completion_tokens=3)),
            ]
        )

    provider = OpenAILLMProvider(api_key="test", model="gpt-test")
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )

    chunks = list(provider.stream_message("system", "user"))

    assert chunks == ["Hola", " mundo"]
    assert captured["stream"] is True
    assert captured["stream_options"] == {"include_usage": True}
    assert captured["messages"][0] == {"role": "system", "content": "system"}
    assert provider.last_usage == LLMUsage(model="gpt-test", input_tokens=12, output_tokens=3)


class _FakeAnthropicStream:
    def __init__(self) -> None:
        self.text_stream = iter(["Esti", "mación"])

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None

    def get_final_message(self) -> SimpleNamespace:
        return SimpleNamespace(usage=SimpleNamespace(input_tokens=20, output_tokens=5))


def test_anthropic_stream_yields_text_and_records_usage() -> None:
    captured = {}

    def fake_stream(**kwargs):
        captured.update(kwargs)
        return _FakeAnthropicStream()

    provider = AnthropicLLMProvider(api_key="test", model="claude-test")
    provider.client = SimpleNamespace(messages=SimpleNamespace(stream=fake_stream))

    chunks = list(provider.stream_message("system", "user"))

    assert chunks == ["Esti", "mación"]
    assert captured["system"] == "system"
    assert captured["messages"] == [{"role": "user", "content": "user"}]
    assert provider.last_usage == LLMUsage(model="claude-test", input_tokens=20, output_tokens=5)
