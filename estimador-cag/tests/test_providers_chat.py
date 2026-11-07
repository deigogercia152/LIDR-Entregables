from types import SimpleNamespace

from app.services.providers.antropic_llm_provider import AnthropicLLMProvider
from app.services.providers.openai_llm_provider import OpenAILLMProvider

HISTORY = [
    {"role": "user", "content": "Primera pregunta"},
    {"role": "assistant", "content": "Primera respuesta"},
    {"role": "user", "content": "Segunda pregunta"},
]


def _openai_provider(captured: dict) -> OpenAILLMProvider:
    def fake_create(**kwargs):
        captured.update(kwargs)
        message = SimpleNamespace(content="respuesta openai")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    provider = OpenAILLMProvider(api_key="test", model="gpt-test")
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )
    return provider


def _anthropic_provider(captured: dict) -> AnthropicLLMProvider:
    def fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="respuesta anthropic")],
            stop_reason="end_turn",
        )

    provider = AnthropicLLMProvider(api_key="test", model="claude-test")
    provider.client = SimpleNamespace(messages=SimpleNamespace(create=fake_create))
    return provider


def test_openai_process_message_payload_is_unchanged() -> None:
    captured: dict = {}

    result = _openai_provider(captured).process_message("system", "user")

    assert result == "respuesta openai"
    assert captured["messages"] == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "user"},
    ]
    assert captured["model"] == "gpt-test"
    assert captured["max_tokens"] == 16000


def test_anthropic_process_message_payload_is_unchanged() -> None:
    captured: dict = {}

    result = _anthropic_provider(captured).process_message("system", "user")

    assert result == "respuesta anthropic"
    assert captured["system"] == "system"
    assert captured["messages"] == [{"role": "user", "content": "user"}]
    assert captured["model"] == "claude-test"
    assert captured["max_tokens"] == 16000


def test_openai_process_chat_sends_system_first_then_the_whole_history() -> None:
    captured: dict = {}

    _openai_provider(captured).process_chat("system", HISTORY)

    assert captured["messages"] == [{"role": "system", "content": "system"}, *HISTORY]


def test_anthropic_process_chat_sends_system_separately_and_the_whole_history() -> None:
    captured: dict = {}

    _anthropic_provider(captured).process_chat("system", HISTORY)

    assert captured["system"] == "system"
    assert captured["messages"] == HISTORY
