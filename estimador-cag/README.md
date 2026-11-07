# Estimador CAG

Servicio IA (FastAPI) y cliente web (Streamlit) para generar estimaciones de
esfuerzo y recursos de proyectos de software. Hay dos formas de usarlo:

- **Conversación con memoria** (`/api/v1/sessions`): el cliente refina el alcance
  turno a turno, adjunta PDFs o documentos Word y el servicio recuerda de qué
  proyecto se habla. Es lo que usa la interfaz de Streamlit.
- **Estimación única** (`/api/v1/estimate`): una petición tipada, sin estado.

Los prompts son templates Jinja2 versionados, fuera del código.

## Requisitos

- Python 3.11 o superior.
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/).
- Una clave de API de OpenAI o Anthropic.

## Instalación y configuración

Desde este directorio (`estimador-cag`), instala las dependencias del proyecto
y las herramientas de prueba con `uv`:

```bash
uv sync --group dev
```

Copia `.env.example` a `.env` y configura el proveedor, su clave y un nombre de
modelo compatible:

```dotenv
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=tu-clave-de-openai
```

Para usar Anthropic, configura `LLM_PROVIDER=anthropic`, indica un modelo de
Anthropic en `LLM_MODEL` (por ejemplo `claude-haiku-4-5-20251001`) y
proporciona `ANTHROPIC_API_KEY`. Solo se necesita la clave del proveedor
seleccionado, y solo la usa el servicio: el cliente no la ve nunca.

## Cómo se levanta

Son dos procesos. En una terminal, el servicio IA:

```bash
uv run uvicorn app.main:app --reload
```

La API queda en `http://127.0.0.1:8000` y su documentación OpenAPI en
`http://127.0.0.1:8000/docs`. Las sesiones viven en la memoria del proceso: usa un
único worker de uvicorn y ten en cuenta que reiniciar el servicio (también con
`--reload`) las borra; el cliente lo detecta y abre una conversación nueva.

En otra terminal, el cliente Streamlit:

```bash
uv run streamlit run streamlit_app.py
```

Se abre en `http://localhost:8501`. Si el servicio está en otra dirección,
indícala con `ESTIMATOR_API_URL`:

```bash
ESTIMATOR_API_URL=http://mi-servidor:8000 uv run streamlit run streamlit_app.py
```

## Endpoints

### `GET /health`

Comprueba que la API está en ejecución:

```json
{"status": "ok"}
```

### `POST /api/v1/estimate`

Recibe un `EstimationRequest` (definido en [`app/schemas.py`](app/schemas.py)):

| Campo           | Valores                                                        |
| --------------- | -------------------------------------------------------------- |
| `description`   | Texto de 20 a 2000 caracteres (sin contar espacios de los extremos) |
| `project_type`  | `mobile_app`, `web_saas`, `internal_tool`, `data_pipeline`     |
| `detail_level`  | `summary`, `medium`, `detailed`                                |
| `output_format` | `phases_table`, `line_items`, `narrative`                      |
| `reference_projects` | Opcional. Hasta 5 proyectos `{name, summary, actual_hours}` ya entregados |

El query param opcional `prompt_version` elige la versión del prompt (`v1` por
defecto, o `v2`): `POST /api/v1/estimate?prompt_version=v2`.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/estimate \
  -H "Content-Type: application/json" \
  -d '{
        "description": "Landing page con formulario de contacto, integración con HubSpot y un blog con editor WYSIWYG.",
        "project_type": "web_saas",
        "detail_level": "medium",
        "output_format": "phases_table"
      }'
```

Devuelve un `EstimationResponse` con el texto generado y la versión del prompt:

```json
{
  "text": "| Fase | Horas | Coste (USD) | confidence_pct | ...",
  "prompt_version": "v1"
}
```

Respuestas de error: `422` si el body no cumple el schema o la versión de prompt
no existe, y `503` si el proveedor no está configurado (por ejemplo, falta la
API key).

### `POST /api/v1/sessions`

Crea una sesión vacía y devuelve su identificador (UUID v4), código `201`:

```json
{"session_id": "288e812e-36d4-4b43-8c0f-c40a6852eddf"}
```

### `POST /api/v1/sessions/{session_id}/estimate`

Un turno de la conversación, como `multipart/form-data`:

| Campo           | Valores                                                               |
| --------------- | --------------------------------------------------------------------- |
| `transcript`    | Texto de 1 a 20 000 caracteres. Sin mínimo de 20: un seguimiento puede ser «¿y con app móvil?» |
| `project_type`  | `mobile_app`, `web_saas`, `internal_tool`, `data_pipeline`            |
| `detail_level`  | `summary`, `medium`, `detailed`                                       |
| `output_format` | `phases_table`, `line_items`, `narrative`                             |
| `attachments`   | Opcional y repetible. PDF o Word `.docx`                              |

```bash
curl -X POST http://127.0.0.1:8000/api/v1/sessions/$SESSION_ID/estimate \
  -F transcript="Web de reservas para un club de pádel con pago online" \
  -F project_type=web_saas -F detail_level=medium -F output_format=line_items \
  -F attachments=@especificacion.pdf -F attachments=@propuesta-previa.docx
```

La respuesta extiende `EstimationResponse` (`text`, `prompt_version`) con el
número de turno y la memoria del proyecto tras este turno:

```json
{
  "text": "1. Modelo de datos ...",
  "prompt_version": "v1",
  "session_id": "288e812e-...",
  "turn": 2,
  "project_metadata": {
    "project_name": "Club Pádel",
    "assumed_team_size": 3,
    "mentioned_technologies": ["Django", "Redis"],
    "agreed_scope": "Web de reservas de pistas con pago online y app móvil"
  }
}
```

Errores: `404` si la sesión no existe, `415` si un adjunto no es PDF ni `.docx`,
`413` si un adjunto supera los límites, `422` si el formulario no es válido o un
adjunto no se puede leer, y `503` si el proveedor no está configurado. Un turno
que falla no se guarda: la sesión queda como estaba y se puede reintentar.

## Memoria conversacional

Se separan dos cosas que suelen confundirse (módulo
[`app/sessions.py`](app/sessions.py)):

- **Historial** (`ConversationHistory`): el array `messages` que viaja al LLM en
  cada llamada. Usa una **ventana deslizante** de `MAX_TURNS = 6` turnos
  completos (un turno es un par usuario + asistente), configurable con
  `SESSION_MAX_TURNS`. El LLM recibe como máximo los 6 últimos pares más el mensaje
  nuevo (13 mensajes); los más antiguos se descartan. `to_messages_list()` devuelve
  ese array con el system prompt regenerado como primer mensaje.
- **Memoria** (`ProjectMetadata`): los hechos del proyecto en curso (`project_name`,
  `assumed_team_size`, `mentioned_technologies`, `agreed_scope`). No se recorta con
  la ventana, así que el nombre del proyecto o el alcance acordado sobreviven
  aunque el turno donde se dijeron ya haya salido del historial. Se inyecta en el
  system prompt en cada turno, dentro de `<project_metadata>` (vacío en el primer
  turno).

Ambas viven en un diccionario en memoria del proceso (máximo `MAX_SESSIONS = 500`,
se expulsa la sesión menos usada). Se acepta esa volatilidad en esta fase: sin
BBDD ni Redis, solo un worker de uvicorn y las sesiones no sobreviven a un reinicio.
Cada sesión tiene un `threading.Lock`: dos peticiones simultáneas a la misma sesión
se ejecutan una detrás de otra en lugar de pisarse el historial.

### Cómo se extrae `project_metadata`

Tras cada estimación, una **segunda llamada al LLM** (extractor, prompt
[`metadata_extraction/v1`](app/prompts/metadata_extraction/v1/)) recibe los hechos
conocidos, el mensaje del cliente y la estimación, y devuelve el JSON con el estado
actualizado. Se fusiona con lo anterior: lo nuevo gana, lo ausente se conserva y las
tecnologías se acumulan sin duplicados.

*Por qué un extractor y no una heurística.* La respuesta del modelo es texto libre
en español con formatos distintos (tabla, lista o narrativa); un regex para sacar
el nombre del proyecto o el alcance fallaría en cuanto cambie el formato. El
extractor cuesta una llamada más por turno (más latencia y tokens), pero es el
mismo código para cualquier formato. Es *best effort*: si falla, o responde algo que
no es el JSON esperado, la estimación se devuelve igual y la memoria anterior se
conserva.

*Seguridad.* Lo que extrae el LLM vuelve al system prompt del turno siguiente, y
puede venir de un adjunto hostil. Por eso `ProjectMetadata` quita `<` y `>`, acota
la longitud de cada campo y el system prompt indica que el texto del cliente y de
los adjuntos es información, no instrucciones.

## Adjuntos: camino B (extracción local)

Se ha elegido el **camino B**: el servicio extrae el texto con `pypdf` (PDF) y
`python-docx` (Word, incluidas las tablas) y lo concatena al mensaje del usuario
tras un separador `--- attachment: nombre.pdf ---`
([`app/attachments.py`](app/attachments.py)).

*Por qué.* El servicio ya abstrae dos proveedores; la Files API ataría los adjuntos
a uno (y a un modelo multimodal), mientras que con texto cualquier proveedor
funciona igual. Además es el paso previo natural al chunking de RAG del módulo 3 y
da control sobre lo que entra en el prompt (límites, saneado). *Qué se pierde:*
diagramas e imágenes dentro de los documentos. Un PDF escaneado (solo imágenes) se
rechaza con un error claro; para esos casos el camino A sería la alternativa.

Límites, que rechazan en lugar de truncar en silencio: 5 adjuntos, 10 MB por
archivo, 60 000 caracteres de texto por archivo y 120 000 entre todos. El nombre del
archivo se reduce a su nombre base sin saltos de línea ni `<>`, porque acaba dentro
del prompt. No se admite el `.doc` antiguo.

## Prompts versionados

Los prompts viven fuera del código, en [`app/prompts/`](app/prompts/), con una
carpeta por prompt y, dentro, una por versión:

```
app/prompts/
├── loader.py
├── estimation/              # /estimate (sin estado)
│   ├── v1/
│   │   ├── system.j2        # rol, instrucciones, bloques según output_format y detail_level
│   │   ├── user.j2          # descripción en <project_description> y proyectos de referencia
│   │   └── examples.j2      # ejemplos few-shot, incluido desde system.j2
│   └── v2/                  # mismo contrato, tono para un cliente no técnico y otros ejemplos
├── session_estimation/      # sesiones: <project_metadata> en el system, adjuntos en el user
│   └── v1/
└── metadata_extraction/     # extractor que actualiza project_metadata
    └── v1/
```

Los prompts de sesión están en su propia carpeta, no como `estimation/v3`: así no
aparecen como una versión válida de `/estimate?prompt_version=...`, donde les
faltarían variables (`StrictUndefined` rompería el render).

`render_estimation_prompt(request, version="v1")` en
[`app/prompts/loader.py`](app/prompts/loader.py) devuelve `(system, user)`, que
se envían al modelo como mensajes `system` y `user` separados. El entorno Jinja2
usa `StrictUndefined`, así que una variable que falte en el contexto rompe el
render en lugar de dejar un hueco silencioso. Las sesiones usan
`render_session_prompt(request, metadata)` y el extractor
`render_metadata_extraction_prompt(...)`. Cada versión tiene su propio
loader, de modo que un `{% include %}` nunca mezcla ficheros de dos versiones.

Para cambiar un prompt ya publicado, crea una carpeta nueva (`v2/`) en lugar de
editar `v1/`: así cada respuesta puede atribuirse a la versión exacta que la
generó (`prompt_version`). Los costes de los ejemplos usan una tarifa ficticia
de USD 50 por hora; no representan precios comerciales.

Si la petición trae `reference_projects`, `user.j2` los recorre con un
`{% for %}` dentro de un bloque `<reference_projects>` para que el modelo
calibre la estimación con horas reales. En el formulario se rellenan en la
tabla "Proyectos de referencia (opcional)".

Cada render emite un evento `prompt_rendered` con structlog que incluye la
versión y un hash del prompt renderizado (nunca la descripción, que puede
contener datos del cliente):

```
[info] prompt_rendered prompt_hash=5b007ed3c39065b3 prompt_name=estimation prompt_version=v1 ...
```

Dos peticiones con el mismo hash recibieron exactamente el mismo prompt.

## Pruebas

Ejecuta las pruebas localmente, sin llamar a OpenAI ni a Anthropic:

```bash
uv run pytest
```

- `tests/test_sessions_api.py` (`httpx.AsyncClient`): el flujo completo de sesiones.
  La memoria se actualiza y se reinyecta entre dos peticiones, un PDF adjunto cambia
  la salida, y tras 8 turnos el historial enviado al LLM nunca pasa de la ventana
  (tamaño exacto, roles alternos y se descarta el par más antiguo).
- `tests/test_sessions.py`: ventana deslizante, fusión y saneado de `ProjectMetadata`,
  expulsión de sesiones.
- `tests/test_attachments.py`: extracción con PDFs y DOCX reales generados en el test,
  formatos no soportados, ficheros falsos, PDF sin texto y límites.
- `tests/prompts/`: templates de estimación (v1, v2), de sesión y del extractor, sin
  red y en milisegundos.
- `tests/test_api.py`: contrato de `/estimate`, que no ha cambiado.
- `tests/test_providers_chat.py`: `process_chat` y que el payload de una sola
  petición no cambia respecto a antes.
- `tests/test_streamlit_app.py`: el cliente con `AppTest` y el HTTP simulado.
- `tests/test_streaming.py`: streaming de los proveedores con el SDK simulado.

Ningún test llama al LLM: usan un doble que distingue la llamada de estimación de la
del extractor. Por eso no pueden demostrar que el modelo real mantiene la coherencia
entre turnos; eso solo se ve con una conversación real.

GitHub Actions ejecuta estas pruebas automáticamente en cada push y pull
request.
