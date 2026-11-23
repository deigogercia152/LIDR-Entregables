# Sanity check de embeddings

Modelo: `text-embedding-3-small` (1536 dimensiones). Similitud coseno calculada con
`scripts/compare.py`. No es una validación formal del modelo: solo comprueba que el
pipeline funciona de punta a punta y que los embeddings separan textos cercanos de
lejanos.

> **ESTADO: PENDIENTE.** Los valores no se han podido calcular porque en el entorno
> donde se preparó la rama no había `OPENAI_API_KEY`. Los comandos de abajo son exactamente
> lo que hay que ejecutar; después, sustituir las `—` por los valores y escribir el
> comentario.

| Pareja | Texto 1 | Texto 2 | Expectativa | Similitud coseno |
| ------ | ------- | ------- | ----------- | ---------------- |
| A (cercanos) | OAuth 2.0 authentication backend with JWT tokens for fintech mobile app | Authorization service using JSON Web Tokens for a banking application | alta (> 0.6) | — |
| B (no relacionados) | OAuth 2.0 authentication backend with JWT tokens for fintech mobile app | Database migration from MySQL to PostgreSQL with zero downtime | baja (< 0.4) | — |
| C (genéricos) | Backend services | API development | sin expectativa fija | — |

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

_Pendiente de rellenar con los resultados reales._
