import httpx
import openai
import pytest
from structlog.testing import capture_logs
from types import SimpleNamespace

from app.embedding_pipeline import embedder as embedder_module
from app.embedding_pipeline.embedder import (
    ChunkTooLargeError,
    OpenAIEmbedder,
    estimate_cost_usd,
)
from app.embedding_pipeline.schemas import Chunk


def rate_limit_error() -> openai.RateLimitError:
    response = httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com/v1/embeddings"))
    return openai.RateLimitError("rate limited", response=response, body=None)


class FakeEmbeddings:
    """Doble de `client.embeddings`: devuelve [longitud del texto, índice] y desordena la respuesta."""

    def __init__(self, failures: list[Exception] | None = None) -> None:
        self.calls: list[list[str]] = []
        self.failures = list(failures or [])

    def create(self, model: str, input: list[str]):
        assert model == "text-embedding-3-small"
        self.calls.append(list(input))
        if self.failures:
            raise self.failures.pop(0)
        data = [SimpleNamespace(index=i, embedding=[float(len(t)), float(i)]) for i, t in enumerate(input)]
        return SimpleNamespace(
            data=list(reversed(data)),  # la API no garantiza el orden: hay que usar `index`
            usage=SimpleNamespace(total_tokens=7 * len(input)),
        )


def make_embedder(fake: FakeEmbeddings) -> tuple[OpenAIEmbedder, list[float]]:
    sleeps: list[float] = []
    embedder = OpenAIEmbedder("test", client=SimpleNamespace(embeddings=fake), sleep=sleeps.append)
    return embedder, sleeps


def make_chunks(count: int, token_count: int = 10) -> list[Chunk]:
    return [
        Chunk(chunk_id=f"B::C{n}", text="x" * (n + 1), metadata={}, token_count=token_count)
        for n in range(count)
    ]


def test_embed_one_returns_the_vector_for_the_text() -> None:
    fake = FakeEmbeddings()
    embedder, _ = make_embedder(fake)

    assert embedder.embed_one("hello") == [5.0, 0.0]
    assert fake.calls == [["hello"]]


def test_embed_many_sends_batches_of_100_not_one_call_per_chunk() -> None:
    fake = FakeEmbeddings()
    embedder, _ = make_embedder(fake)

    result = embedder.embed_many(make_chunks(250))

    assert [len(call) for call in fake.calls] == [100, 100, 50]
    assert len(result) == 250


def test_embed_many_keeps_each_vector_with_its_own_chunk_even_if_the_api_reorders() -> None:
    fake = FakeEmbeddings()
    embedder, _ = make_embedder(fake)
    chunks = make_chunks(5)

    result = embedder.embed_many(chunks)

    assert [item.chunk_id for item in result] == [chunk.chunk_id for chunk in chunks]
    assert [item.embedding[0] for item in result] == [1.0, 2.0, 3.0, 4.0, 5.0]  # len(text)
    assert result[2].text == chunks[2].text and result[2].token_count == 10


def test_embed_many_with_no_chunks_makes_no_api_call() -> None:
    fake = FakeEmbeddings()
    embedder, _ = make_embedder(fake)

    assert embedder.embed_many([]) == []
    assert fake.calls == []


def test_rate_limit_errors_are_retried_with_1_2_4_second_waits() -> None:
    fake = FakeEmbeddings(failures=[rate_limit_error(), rate_limit_error(), rate_limit_error()])
    embedder, sleeps = make_embedder(fake)

    result = embedder.embed_many(make_chunks(2))

    assert len(result) == 2
    assert len(fake.calls) == 4  # 3 fallos + 1 éxito
    assert sleeps == [1, 2, 4]


def test_rate_limit_is_raised_after_three_retries() -> None:
    fake = FakeEmbeddings(failures=[rate_limit_error() for _ in range(4)])
    embedder, sleeps = make_embedder(fake)

    with pytest.raises(openai.RateLimitError):
        embedder.embed_many(make_chunks(1))

    assert len(fake.calls) == 4
    assert sleeps == [1, 2, 4]


def test_other_errors_are_not_retried() -> None:
    request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    fake = FakeEmbeddings(failures=[openai.APIConnectionError(request=request)])
    embedder, sleeps = make_embedder(fake)

    with pytest.raises(openai.APIConnectionError):
        embedder.embed_many(make_chunks(1))

    assert len(fake.calls) == 1
    assert sleeps == []


def test_a_chunk_over_the_model_limit_is_rejected_before_calling_the_api() -> None:
    fake = FakeEmbeddings()
    embedder, _ = make_embedder(fake)
    chunks = make_chunks(2) + [
        Chunk(chunk_id="B::HUGE", text="x", metadata={}, token_count=embedder_module.MAX_INPUT_TOKENS + 1)
    ]

    with pytest.raises(ChunkTooLargeError, match="B::HUGE"):
        embedder.embed_many(chunks)

    assert fake.calls == []


def test_every_batch_is_logged_with_chunks_tokens_and_latency() -> None:
    fake = FakeEmbeddings()
    embedder, _ = make_embedder(fake)

    with capture_logs() as logs:
        embedder.embed_many(make_chunks(150))

    batches = [log for log in logs if log["event"] == "embedding_batch"]
    assert [(b["chunks"], b["tokens"]) for b in batches] == [(100, 700), (50, 350)]
    assert all(b["latency_ms"] >= 0 and b["model"] == "text-embedding-3-small" for b in batches)


def test_cost_is_two_cents_per_million_tokens() -> None:
    assert estimate_cost_usd(1_000_000) == 0.02
    assert estimate_cost_usd(0) == 0
    assert estimate_cost_usd(9_000) == pytest.approx(0.00018)
