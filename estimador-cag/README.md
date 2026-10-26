# Estimador CAG

API REST para generar estimaciones de esfuerzo y recursos para proyectos de
software a partir de transcripciones de reuniones con clientes. La estimación
incluye tareas y horas, total estimado, equipo recomendado y duración.

## Requisitos

- Python 3.11 o superior.
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/).
- Una clave de API de OpenAI o Anthropic.

## Instalación y ejecución

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
Anthropic en `LLM_MODEL` y proporciona `ANTHROPIC_API_KEY`. Solo se necesita la
clave del proveedor seleccionado.

Inicia el servidor desde `estimador-cag`:

```bash
uv run uvicorn app.main:app --reload
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

Envía una transcripción no vacía como JSON. Hay un ejemplo listo para probar en
[`data/transcripcion_reunion.txt`](data/transcripcion_reunion.txt):

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

## Interfaz web (Streamlit)

Además de la API, el proyecto incluye una interfaz de chat en
[`streamlit_app.py`](streamlit_app.py). Llama directamente a la capa de
servicios, así que no hace falta tener uvicorn levantado. Desde
`estimador-cag`:

```bash
uv run streamlit run streamlit_app.py
```

Se abre en `http://localhost:8501`. Pega una transcripción (por ejemplo, la de
[`data/transcripcion_reunion.txt`](data/transcripcion_reunion.txt)) y la
estimación se irá mostrando en streaming. Cada mensaje se estima de forma
independiente con el mismo system prompt y los mismos ejemplos que el endpoint;
el historial se mantiene en pantalla durante la sesión.

El panel lateral muestra el system prompt activo, las estimaciones de ejemplo
inyectadas y las métricas de la última llamada (modelo, tokens de entrada y
salida, tiempo de respuesta). El botón "Nueva conversación" vacía el historial.

La configuración se lee de `.env`. Como alternativa, puedes copiar
`.streamlit/secrets.toml.example` a `.streamlit/secrets.toml` (ignorado en git);
sus valores tienen prioridad sobre `.env` salvo que la variable ya exista en el
entorno.

## Contexto de estimaciones

La API inyecta tres ejemplos estáticos definidos en
[`app/context/examples.py`](app/context/examples.py) en cada petición. Los
costes de esos ejemplos son orientativos y se calculan con una tarifa ficticia
de USD 50 por hora; no representan precios comerciales.

## Pruebas y validación automática

Ejecuta las pruebas localmente sin llamar a OpenAI ni Anthropic:

```bash
uv run pytest
```

GitHub Actions ejecuta estas pruebas automáticamente en cada push y pull
request.