"""Compara dos textos: los embebe con OpenAI y muestra su similitud coseno.

    uv run python scripts/compare.py --text-a "..." --text-b "..."
    docker compose exec servicio_ia python scripts/compare.py --text-a "..." --text-b "..."
"""

import argparse
import math
import sys
from pathlib import Path

# `python scripts/compare.py` pone scripts/ en sys.path, no la raíz del proyecto.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.embedding_pipeline.embedder import OpenAIEmbedder  # noqa: E402


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Producto escalar dividido por el producto de las normas, solo con la biblioteca estándar."""
    if len(a) != len(b):
        raise ValueError(f"Los vectores tienen distinta dimensión: {len(a)} y {len(b)}.")
    norm_a, norm_b = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        raise ValueError("No se puede calcular la similitud con un vector de norma cero.")
    return sum(x * y for x, y in zip(a, b)) / (norm_a * norm_b)


def main(argv: list[str] | None = None, embedder: OpenAIEmbedder | None = None) -> int:
    parser = argparse.ArgumentParser(description="Similitud coseno entre dos textos.")
    parser.add_argument("--text-a", required=True)
    parser.add_argument("--text-b", required=True)
    args = parser.parse_args(argv)

    if embedder is None:
        if not settings.openai_api_key:
            print("Falta OPENAI_API_KEY (defínela en .env o en el entorno).", file=sys.stderr)
            return 1
        embedder = OpenAIEmbedder(settings.openai_api_key)

    similarity = cosine_similarity(embedder.embed_one(args.text_a), embedder.embed_one(args.text_b))
    print(f"Text A: {args.text_a}")
    print(f"Text B: {args.text_b}")
    print(f"Cosine similarity: {similarity:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
