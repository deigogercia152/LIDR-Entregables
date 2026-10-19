# Estimador CAG

API REST para generar estimaciones de esfuerzo y recursos para proyectos de
software a partir de transcripciones de reuniones con clientes. La estimación
incluye tareas y horas, total estimado, equipo recomendado y duración.

## Requisitos

- Python 3.11 o superior.
- Una clave de API de OpenAI o Anthropic.

## Instalación y ejecución

Desde este directorio (`estimador-cag`), crea y activa un entorno virtual e
instala las dependencias:

```bash
python -m venv .venv
source .venv/bin/activate
pip install fastapi "uvicorn[standard]" pydantic-settings openai anthropic python-dotenv
```

Copia `.env.example` a `.env` y configura el proveedor, su clave y un nombre de
modelo compatible:

```dotenv
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=tu-clave-de-openai
```

Para usar Anthropic, configura `LLM_PROVIDER=anthropic`, indica un modelo de
Anthropic en `LLM_MODEL` y proporciona `ANTHROPIC_API_KEY`. Solo se necesita la
clave del proveedor seleccionado.

Inicia el servidor desde `estimador-cag`:

```bash
uvicorn app.main:app --reload
```

La API estará disponible en `http://127.0.0.1:8000`. La documentación
interactiva de OpenAPI está en `http://127.0.0.1:8000/docs`.

## Endpoints

### `GET /health`

Comprueba que la API está en ejecución:

```json
{"status": "ok"}
```

### `POST /api/v1/estimate`

Envía una transcripción no vacía como JSON:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/estimate \
  -H "Content-Type: application/json" \
  -d '{"transcription":"El cliente necesita una aplicación web para gestionar inventario y generar reportes."}'
```

La respuesta contiene la estimación generada, el modelo y el proveedor:

```json
{
  "estimation": "## Estimación ...",
  "model": "gpt-4o-mini",
  "provider": "openai"
}

```