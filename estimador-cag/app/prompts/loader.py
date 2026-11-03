import hashlib
from functools import lru_cache
from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.schemas import EstimationRequest

logger = structlog.get_logger(__name__)

ESTIMATION_PROMPTS_DIR = Path(__file__).resolve().parent / "estimation"
DEFAULT_PROMPT_VERSION = "v1"


def available_versions() -> list[str]:
    """Devuelve las versiones de prompt de estimación que existen en disco."""
    return sorted(path.name for path in ESTIMATION_PROMPTS_DIR.iterdir() if path.is_dir())


@lru_cache
def _get_environment(version: str) -> Environment:
    """Crea un entorno Jinja2 por versión.

    Cada versión tiene su propio loader, así los `{% include %}` de una versión
    resuelven siempre a ficheros de esa misma versión.
    """
    if version not in available_versions():
        raise ValueError(f"Versión de prompt desconocida: {version!r}")

    return Environment(
        loader=FileSystemLoader(ESTIMATION_PROMPTS_DIR / version),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,
    )


def render_estimation_prompt(
    request: EstimationRequest,
    version: str = DEFAULT_PROMPT_VERSION,
) -> tuple[str, str]:
    """
    Renderiza los mensajes de sistema y de usuario para una estimación.

    Args:
        request (EstimationRequest): Parámetros tipados de la estimación.
        version (str): Versión del prompt (carpeta dentro de `estimation/`).

    Returns:
        tuple[str, str]: `(system, user)` listos para enviar al modelo.
    """
    environment = _get_environment(version)
    context = request.model_dump(mode="json")

    system = environment.get_template("system.j2").render(**context).strip()
    user = environment.get_template("user.j2").render(**context).strip()

    # Solo el hash: la descripción puede contener datos del cliente.
    prompt_hash = hashlib.sha256(f"{system}\n{user}".encode()).hexdigest()[:16]
    logger.info(
        "prompt_rendered",
        prompt_name="estimation",
        prompt_version=version,
        prompt_hash=prompt_hash,
        system_chars=len(system),
        user_chars=len(user),
    )
    return system, user
