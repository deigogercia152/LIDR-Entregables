import time
from collections.abc import Callable

import openai
import structlog
from openai import OpenAI

from app.embedding_pipeline.chunker import EMBEDDING_MODEL
from app.embedding_pipeline.schemas import Chunk, EmbeddedChunk

logger = structlog.get_logger(__name__)

# Precio de entrada de text-embedding-3-small en USD por millón de tokens.
# OJO: cambia con el tiempo; revísalo en https://openai.com/api/pricing antes de fiarte del coste.
PRICE_PER_MILLION_TOKENS_USD = 0.02
BATCH_SIZE = 100
MAX_INPUT_TOKENS = 8191  # límite de entrada del modelo por texto
RETRY_DELAYS_SECONDS = (1, 2, 4)


class ChunkTooLargeError(ValueError):
    """Un chunk supera el límite de tokens del modelo. No se parte: se avisa antes de llamar a la API."""


def estimate_cost_usd(total_tokens: int) -> float:
    return total_tokens * PRICE_PER_MILLION_TOKENS_USD / 1_000_000


class OpenAIEmbedder:
    def __init__(
        self,
        api_key: str,
        client: OpenAI | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client or OpenAI(api_key=api_key)
        self._sleep = sleep

    def embed_one(self, text: str) -> list[float]:
        return self._embed_batch([text])[0]

    def embed_many(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        for chunk in chunks:
            if chunk.token_count > MAX_INPUT_TOKENS:
                raise ChunkTooLargeError(
                    f"Chunk {chunk.chunk_id} has {chunk.token_count} tokens; "
                    f"{EMBEDDING_MODEL} accepts at most {MAX_INPUT_TOKENS}."
                )

        embedded: list[EmbeddedChunk] = []
        # shortcut: batches por número de chunks; con chunks muy grandes (cerca de 8191 tokens)
        # la API podría rechazar el total por petición. Subir a batching por tokens si pasa.
        for start in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[start : start + BATCH_SIZE]
            vectors = self._embed_batch([chunk.text for chunk in batch])
            embedded += [
                EmbeddedChunk(**chunk.model_dump(), embedding=vector)
                for chunk, vector in zip(batch, vectors, strict=True)
            ]
        return embedded

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        start = time.perf_counter()
        response = self._create_with_retries(texts)
        logger.info(
            "embedding_batch",
            model=EMBEDDING_MODEL,
            chunks=len(texts),
            tokens=response.usage.total_tokens,
            latency_ms=round((time.perf_counter() - start) * 1000),
        )
        # La API devuelve un `index` por vector: no se asume que lleguen en orden.
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]

    def _create_with_retries(self, texts: list[str]):
        for delay in (*RETRY_DELAYS_SECONDS, None):
            try:
                return self._client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
            except openai.RateLimitError:
                if delay is None:
                    raise
                logger.warning("embedding_rate_limited", retry_in_seconds=delay)
                self._sleep(delay)
