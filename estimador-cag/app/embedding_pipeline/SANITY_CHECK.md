# Sanity check de embeddings

Modelo: `text-embedding-3-small` (1536 dimensiones). Similitud coseno calculada con
`scripts/compare.py`. No es una validación formal del modelo: solo comprueba que el
pipeline funciona de punta a punta y que los embeddings separan textos cercanos de
lejanos.

| Pareja | Texto 1 | Texto 2 | Expectativa | Similitud coseno |
| ------ | ------- | ------- | ----------- | ---------------- |
| A (cercanos) | OAuth 2.0 authentication backend with JWT tokens for fintech mobile app | Authorization service using JSON Web Tokens for a banking application | alta (> 0.6) | **0.5957** |
| B (no relacionados) | OAuth 2.0 authentication backend with JWT tokens for fintech mobile app | Database migration from MySQL to PostgreSQL with zero downtime | baja (< 0.4) | **0.1920** |
| C (genéricos) | Backend services | API development | sin expectativa fija | **0.5407** |

## Cómo reproducirlo

Desde `estimador-cag/`, con `OPENAI_API_KEY` en `.env`:

```bash
uv run python scripts/compare.py \
  --text-a "OAuth 2.0 authentication backend with JWT tokens for fintech mobile app" \
  --text-b "Authorization service using JSON Web Tokens for a banking application"

uv run python scripts/compare.py \
  --text-a "OAuth 2.0 authentication backend with JWT tokens for fintech mobile app" \
  --text-b "Database migration from MySQL to PostgreSQL with zero downtime"

uv run python scripts/compare.py \
  --text-a "Backend services" \
  --text-b "API development"
```

## Comentario

- **A (0.5957):** los textos son casi sinónimos y aun así queda un pelo por debajo del 0.6 orientativo. Comparten pocas palabras (OAuth/JWT frente a «JSON Web Tokens», «fintech» frente a «banking»); una posible explicación es que el vocabulario distinto le resta similitud. Sigue muy por encima de la pareja B.
- **B (0.1920):** claramente baja, como se esperaba. La separación entre A y B (~0.40) es lo que importa: el modelo discrimina.
- **C (0.5407):** lo más llamativo. Dos textos genéricos de dos palabras cada uno puntúan casi igual que la pareja A, que es un caso de equivalencia real. Con una sola pareja no se puede concluir nada, pero encaja con la idea de que los textos cortos y vagos dan similitudes infladas y de que un chunk sin contexto sería poco discriminante (por eso el chunker antepone el contexto del presupuesto padre).
- El umbral 0.6 es orientativo: el valor absoluto del coseno depende del modelo, así que conviene comparar entre parejas y no fiarse de un corte fijo.
