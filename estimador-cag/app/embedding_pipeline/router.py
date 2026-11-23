import structlog
from fastapi import APIRouter, Depends, HTTPException
from openai import OpenAIError

from app.config import settings
from app.embedding_pipeline.chunker import JSONStructuralChunker
from app.embedding_pipeline.embedder import ChunkTooLargeError, OpenAIEmbedder, estimate_cost_usd
from app.embedding_pipeline.schemas import IngestRequest, IngestResponse, IngestStats

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["embeddings"])


def get_embedder() -> OpenAIEmbedder:
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY no está configurada.")
    return OpenAIEmbedder(settings.openai_api_key)


@router.post("/ingest", response_model=IngestResponse)
def ingest(request: IngestRequest, embedder: OpenAIEmbedder = Depends(get_embedder)) -> IngestResponse:
    chunks = JSONStructuralChunker().chunk(request.budgets)
    try:
        embedded = embedder.embed_many(chunks)
    except ChunkTooLargeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except OpenAIError:
        # El detalle (que puede incluir fragmentos de la clave) solo va al log, no al cliente.
        logger.exception("embedding_failed")
        raise HTTPException(status_code=500, detail="Embedding service error") from None

    total_tokens = sum(chunk.token_count for chunk in chunks)
    return IngestResponse(
        chunks=embedded,
        stats=IngestStats(
            total_budgets=len(request.budgets),
            total_chunks=len(chunks),
            total_tokens=total_tokens,
            estimated_cost_usd=round(estimate_cost_usd(total_tokens), 6),
        ),
    )
