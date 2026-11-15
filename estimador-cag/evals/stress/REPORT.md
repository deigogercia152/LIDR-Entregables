# REPORT — baseline cuantitativo del CAG

Sesión 6 · `claude-haiku-5-5` (Anthropic, único proveedor) · 198 filas en
[`results.csv`](results.csv) · 3 repeticiones por celda · coste total de la corrida 0,58 USD.
Se mide; no se optimiza ninguna constante (`MAX_TURNS=6`, `MAX_TEXT_CHARS_PER_FILE=60000` intactas).

## Qué se midió y qué no (leer antes de las tablas)

- **El servicio no tenía la base de la sesión 5.** La rama `pre-session-05` no traía ni caches, ni summarizer,
  ni anclas, ni tier dinámico, ni `evals/`. Se añadió solo lo necesario para medir: wrapper observable
  (`latency_ms`, tokens, `cost_usd`) y el evento `turn_observed`. Por eso `exact hit`, `semantic hit` valen
  **0 % por construcción** (no existen caches) y `anchors_count`, `summary_chars` valen 0: el recall de
  memoria solo puede venir de **`ProjectMetadata`** (4 campos) o, como columna aparte, de la **ventana**.
- `latency_ms`, `tokens_*` y `cost_usd` son **totales del turno**: estimación + extractor de metadata (2 llamadas).
  Una única petición a la vez, sin concurrencia. El latency P95 sale de 3 repeticiones por celda: es orientativo.
- Tamaños de adjunto en **KB de texto extraído** (≈ N·1000 caracteres). Se añadió 55 KB (no pedido) para medir
  justo por debajo del tope de 60.000 caracteres.
- Las curvas «vs N» se leen de una única conversación de 20 turnos por repetición (la de N turnos es su prefijo).
- Las métricas viven en `evals/stress/metrics.py` y no en un `evals/metrics.py` general porque dependen del shape
  de `turn_observed` y del snapshot de sesión, no de una `EstimationResult` (que aquí no existe).

## Tabla resumen

Escenarios multi-turno: 20 turnos × 3 repeticiones. «recall (memoria)» = facts declarados antes que siguen en
summary/anchors/metadata; «+ventana» suma los mensajes aún dentro de la ventana de 6 turnos.

| escenario | adjunto KB | filas | errores HTTP | P50 latency ms | P95 latency ms | coste total USD | coste medio/turno USD | exact hit | semantic hit | recall medio (memoria) | recall medio (+ventana) | recall adjunto |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attachments | 0 | 3 | 0 | 9667 | 10783 | 0.0037 | 0.00125 | 0% | 0% | – | – | – |
| attachments | 5 | 3 | 0 | 19171 | 19610 | 0.0086 | 0.00286 | 0% | 0% | – | – | 1.00 |
| attachments | 20 | 3 | 0 | 19565 | 21260 | 0.0119 | 0.00396 | 0% | 0% | – | – | 1.00 |
| attachments | 50 | 3 | 0 | 21366 | 22323 | 0.0190 | 0.00633 | 0% | 0% | – | – | 1.00 |
| attachments | 55 | 3 | 0 | 21450 | 22017 | 0.0198 | 0.00662 | 0% | 0% | – | – | 1.00 |
| attachments | 100 | 3 | 3 | nan | nan | 0.0000 | – | 0% | 0% | – | – | – |
| contradiction | 0 | 60 | 0 | 6909 | 11800 | 0.1105 | 0.00184 | 0% | 0% | 0.45 | 0.75 | – |
| growing | 0 | 60 | 0 | 17931 | 26616 | 0.2240 | 0.00373 | 0% | 0% | 0.81 | 0.94 | – |
| pivot | 0 | 60 | 0 | 13141 | 19778 | 0.1786 | 0.00298 | 0% | 0% | 1.00 | 1.00 | – |

Presupuestos evaluados turno a turno: `LatencyBudgetMetric(4000 ms)` **0 % de aciertos** (195 turnos OK, el más
rápido 4.482 ms); `CostBudgetMetric(0,01 USD)` **100 %** (máximo 0,0067 USD por turno).

## Curva 1 — latencia vs tokens

| tokens_in (rango) | n | latency ms medio | P95 ms | tokens_out medio | coste medio USD |
|---|---|---|---|---|---|
| 0–3000 | 1 | 8340 | 8340 | 1597 | 0.00110 |
| 3000–6000 | 27 | 10161 | 13700 | 2188 | 0.00151 |
| 6000–10000 | 43 | 9231 | 18139 | 2151 | 0.00191 |
| 10000–15000 | 64 | 11124 | 19674 | 2725 | 0.00263 |
| 15000–25000 | 48 | 18609 | 22811 | 4710 | 0.00434 |
| ≥25000 | 12 | 23671 | 28495 | 5738 | 0.00631 |

Por turno (media de 3 repeticiones; celdas `tokens_in / latency ms`):

| turno N | contradiction tokens_in / ms | growing tokens_in / ms | pivot tokens_in / ms |
|---|---|---|---|
| 1 | 3151 / 11994 | 3204 / 13884 | 3273 / 11303 |
| 3 | 5419 / 9024 | 5808 / 8693 | 5808 / 12681 |
| 6 | 9527 / 8731 | 10523 / 11200 | 11059 / 17743 |
| 10 | 11648 / 7274 | 15820 / 16434 | 16265 / 16516 |
| 20 | 10225 / 5611 | 27142 / 25325 | 15720 / 12941 |

La latencia correlaciona con `tokens_out` (r = 0,98), no tanto con `tokens_in` (r = 0,67): ≈ 4,2 ms por token
generado. La subida con los tokens de entrada es en buena parte la subida de la longitud de las respuestas.

## Curva 2 — coste acumulado (USD) vs turno

| turno N | contradiction | growing | pivot |
|---|---|---|---|
| 1 | 0.0016 | 0.0018 | 0.0015 |
| 3 | 0.0046 | 0.0048 | 0.0048 |
| 6 | 0.0106 | 0.0113 | 0.0132 |
| 10 | 0.0188 | 0.0255 | 0.0264 |
| 20 | 0.0368 | 0.0747 | 0.0595 |

Coste **por turno** del turno 20 frente al 1: ×3,4 en `growing` (tokens_in ×8,5), ×2,2 en `pivot`, ×1,1 en
`contradiction`. Acumulado de `growing` al turno 20: 0,0747 USD frente a 0,0018 USD del primer turno.

## Curva 3 — recall del fact-tracker vs N (memoria / +ventana)

| turno N | contradiction memoria / +ventana | growing memoria / +ventana | pivot memoria / +ventana |
|---|---|---|---|
| 1 | – | – | – |
| 3 | 1.00 / 1.00 | 1.00 / 1.00 | 1.00 / 1.00 |
| 6 | 0.50 / 1.00 | 0.80 / 1.00 | 1.00 / 1.00 |
| 10 | 0.33 / 1.00 | 0.81 / 0.89 | 1.00 / 1.00 |
| 20 | 0.33 / 0.33 | 0.72 / 0.91 | 1.00 / 1.00 |

En `contradiction`, recall con ventana por turno: **1,00 hasta el turno 13 y 0,33 desde el turno 14** (en
todas las repeticiones). Los facts `30000` y `80000` están en `ProjectMetadata` en **0 de 51** turnos medibles (3 repeticiones × turnos 4–20).
En `pivot`, `React` sigue en `mentioned_technologies` junto a `Flutter` del turno 6 al 20 en las 3 repeticiones
(`stale_present = 1`). En `growing`, `audit log` no llegó a la metadata en ninguna repetición y `notificaciones` solo en una
(12 turnos) antes de perderse; el nombre `Nimbus` sobrevivió en 57/57 turnos medibles (2–20).

## Escenario de adjuntos (mismo transcript, mismo `project_type`)

| adjunto KB | HTTP | chars extraídos | tokens_in | latency ms | coste USD | recall canarios |
|---|---|---|---|---|---|---|
| 0 | 200 | 0 | 3065 | 9638 | 0.00125 | – |
| 5 | 200 | 5359 | 7785 | 19051 | 0.00286 | 1.00 |
| 20 | 200 | 20299 | 18415 | 19700 | 0.00396 | 1.00 |
| 50 | 200 | 50277 | 39902 | 21721 | 0.00633 | 1.00 |
| 55 | 200 | 55264 | 43245 | 21385 | 0.00662 | 1.00 |
| 100 | 413 | – | – | – | – | – |

`recall canarios` = fracción de los tres ERP (principio, mitad y final del documento) que aparecen en la
respuesta. A 100 KB el servicio **no trunca: devuelve 413** (`demasiado texto`, tope 60.000 caracteres).

## Dónde empieza a romperse mi CAG y por qué

**El CAG no se rompe por capacidad de contexto; se rompe por memoria, y lo hace en silencio.** Con 43.245
tokens de entrada (adjunto de 55 KB) el modelo encuentra los tres canarios (recall 1,00 en todos los tamaños que
entran) y ningún turno supera 0,0067 USD, así que ni el contexto ni el presupuesto de coste se agotan. Lo que
falla es lo que sale de la ventana de 6 turnos y no cabe en los 4 campos de `ProjectMetadata`. En
`contradiction` los presupuestos de 30000 y 80000 EUR no se persistieron nunca (0 de 51 turnos medibles): solo viven en la
ventana, y el recall cae de 1,00 a 0,33 **en el turno 14**, justo cuando el turno 8 sale de la ventana. No hay
excepción, el esquema es válido y ningún test rojo avisa: es la degradación silenciosa del objetivo 1, bastante
más peligrosa que un fallo duro. `pivot` muestra el otro lado: la metadata acumula y nunca retracta, así que
tras el cambio a Flutter el stack declara React y Flutter a la vez (3/3 repeticiones). En `growing` el recall de
memoria queda en 0,72 en el turno 20 (0,91 contando la ventana), con `audit log` que jamás entró y `notificaciones` que apenas lo hizo.

**La dimensión que domina el daño es la memoria; la que domina la molestia es la latencia; el coste es la
que escala pero aún sobra margen.** El presupuesto de 4 s falla en el 100 % de los turnos, incluido el
primero (mínimo 4,5 s), pero es un problema del tamaño de la respuesta (≈ 4,2 ms por token generado,
r = 0,98), no del contexto acumulado: un solo PDF de 5 KB ya duplica la latencia (9,6 s → 19,1 s) porque la
respuesta pasa de 1.886 a 4.171 tokens. El coste sí crece con el historial: ×3,4 por turno en `growing`
(tokens de entrada ×8,5 hasta 27.142) y 5,3× el de la base con el adjunto de 55 KB, pero todo cabe en el
presupuesto. Casos límite que justifican saltar a RAG: (1) documentos por encima de 60.000 caracteres, que
hoy fallan con 413 en lugar de degradar; (2) hechos que deben sobrevivir a la ventana y no caben en la
metadata (un presupuesto, una decisión), donde recuperar por consulta sustituye a esperar que el extractor los
promueva; (3) proyectos que crecen, donde el historial pasa de 3.204 a 27.142 tokens de entrada en 20 turnos.
Limitaciones: un solo modelo, 3 repeticiones, tres canarios por documento y facts buscados por coincidencia
exacta (un hecho reformulado por el LLM cuenta como perdido).

## Cómo reproducirlo

```bash
uv run uvicorn app.main:app &
uv run python -m evals.stress.run --http http://localhost:8000 \
    --scenarios growing,pivot,contradiction --attachment-sizes 0,5,20,50,55,100 \
    --repeats 3 --output evals/stress/results.csv
uv run python -m evals.stress.report evals/stress/results.csv
```
