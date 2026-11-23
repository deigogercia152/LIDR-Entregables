from functools import lru_cache

import tiktoken

from app.embedding_pipeline.schemas import Budget, Chunk

EMBEDDING_MODEL = "text-embedding-3-small"


@lru_cache
def _encoding() -> tiktoken.Encoding:
    return tiktoken.encoding_for_model(EMBEDDING_MODEL)


class JSONStructuralChunker:
    """Un componente del presupuesto = un chunk.

    No hay overlap ni se parte una descripción larga: se confía en la estructura del JSON.
    El texto lleva delante el contexto del presupuesto padre (proyecto, sector, año, tecnología)
    para que un componente como «Authentication backend» no pierda a qué cliente pertenece.
    """

    def chunk(self, budgets: list[Budget]) -> list[Chunk]:
        return [
            self._chunk_component(budget, component)
            for budget in budgets
            for component in budget.components
        ]

    def _chunk_component(self, budget: Budget, component) -> Chunk:
        text = (
            f"[Project: {budget.project_summary}]\n"
            f"[Client sector: {budget.client_metadata.sector} | Year: {budget.year} "
            f"| Main tech: {budget.main_technology}]\n"
            "\n"
            f"Component: {component.name}\n"
            f"Description: {component.description}\n"
            f"Tech stack: {', '.join(component.tech_stack)}\n"
            f"Complexity: {component.complexity}\n"
            f"Estimated hours: {component.estimated_hours:g}"
        )
        return Chunk(
            chunk_id=f"{budget.budget_id}::{component.component_id}",
            text=text,
            metadata={
                "budget_id": budget.budget_id,
                "component_id": component.component_id,
                "client_sector": budget.client_metadata.sector,
                "main_technology": budget.main_technology,
                "year": budget.year,
                "complexity": component.complexity,
                "estimated_hours": component.estimated_hours,
            },
            # disallowed_special=(): un texto con «<|endoftext|>» se cuenta como texto normal.
            token_count=len(_encoding().encode(text, disallowed_special=())),
        )
