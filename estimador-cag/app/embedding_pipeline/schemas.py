from typing import Literal

from pydantic import BaseModel, Field, model_validator

MAX_BUDGETS_PER_REQUEST = 100  # cada presupuesto cuesta tokens de embeddings: acota el gasto por petición


class ClientMetadata(BaseModel):
    name: str = Field(min_length=1)
    # Abierto a propósito: el universo de sectores del dataset no está cerrado.
    sector: str = Field(min_length=1)
    country: str = Field(min_length=1)


class BudgetComponent(BaseModel):
    component_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    tech_stack: list[str]
    estimated_hours: float = Field(ge=0)
    complexity: Literal["low", "medium", "high"]
    dependencies: list[str] = Field(default_factory=list)


class Budget(BaseModel):
    budget_id: str = Field(min_length=1)
    client_metadata: ClientMetadata
    project_summary: str = Field(min_length=1)
    main_technology: str = Field(min_length=1)
    year: int = Field(ge=1990, le=2100)
    total_estimated_hours: float = Field(ge=0)
    components: list[BudgetComponent] = Field(min_length=1)


class Chunk(BaseModel):
    chunk_id: str
    text: str
    # Campos filtrables: viajan con el chunk, no se embeben.
    metadata: dict[str, str | int | float]
    token_count: int = Field(ge=0)


class EmbeddedChunk(Chunk):
    embedding: list[float]


class IngestRequest(BaseModel):
    budgets: list[Budget] = Field(min_length=1, max_length=MAX_BUDGETS_PER_REQUEST)

    @model_validator(mode="after")
    def chunk_ids_must_be_unique(self) -> "IngestRequest":
        ids = [f"{b.budget_id}::{c.component_id}" for b in self.budgets for c in b.components]
        duplicated = sorted({chunk_id for chunk_id in ids if ids.count(chunk_id) > 1})
        if duplicated:
            raise ValueError(f"Repeated budget_id::component_id: {', '.join(duplicated)}")
        return self


class IngestStats(BaseModel):
    total_budgets: int
    total_chunks: int
    total_tokens: int
    estimated_cost_usd: float


class IngestResponse(BaseModel):
    chunks: list[EmbeddedChunk]
    stats: IngestStats
