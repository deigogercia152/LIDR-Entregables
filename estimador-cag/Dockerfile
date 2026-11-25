FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv

WORKDIR /app

# Dependencias primero: la capa se cachea mientras no cambie pyproject.toml.
# uv.lock está en .gitignore, así que se resuelve en el build.
COPY pyproject.toml ./
RUN uv sync --no-install-project --no-dev

COPY app ./app
COPY scripts ./scripts
COPY data ./data

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

# La clave de OpenAI NO va en la imagen: llega por env_file/entorno al arrancar.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
