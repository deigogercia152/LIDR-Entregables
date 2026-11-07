import hashlib
from functools import lru_cache
from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.schemas import EstimationRequest, SessionEstimationRequest
from app.sessions import ProjectMetadata

logger = structlog.get_logger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent
DEFAULT_PROMPT_VERSION = "v1"


def available_versions(name: str = "estimation") -> list[str]:
    """Devuelve las versiones que existen en disco de un prompt (carpeta bajo `prompts/`)."""
    return sorted(path.name for path in (PROMPTS_DIR / name).iterdir() if path.is_dir())


@lru_cache
def _get_environment(name: str, version: str) -> Environment:
    """Crea un entorno Jinja2 por prompt y versión.

    Cada versión tiene su propio loader, así los `{% include %}` de una versión
    resuelven siempre a ficheros de esa misma versión.
    """
    if version not in available_versions(name):
        raise ValueError(f"Versión de prompt desconocida: {version!r}")

    return Environment(
        loader=FileSystemLoader(PROMPTS_DIR / name / version),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,
    )


def _render(name: str, version: str, context: dict) -> tuple[str, str]:
    environment = _get_environment(name, version)
    system = environment.get_template("system.j2").render(**context).strip()
    user = environment.get_template("user.j2").render(**context).strip()

    # Solo el hash: el texto puede contener datos del cliente.
    prompt_hash = hashlib.sha256(f"{system}\n{user}".encode()).hexdigest()[:16]
    logger.info(
        "prompt_rendered",
        prompt_name=name,
        prompt_version=version,
        prompt_hash=prompt_hash,
        system_chars=len(system),
        user_chars=len(user),
    )
    return system, user


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
    return _render("estimation", version, request.model_dump(mode="json"))


def render_session_prompt(
    request: SessionEstimationRequest,
    metadata: ProjectMetadata,
    version: str = DEFAULT_PROMPT_VERSION,
) -> tuple[str, str]:
    """Renderiza un turno de sesión: el system lleva `<project_metadata>`, el user los adjuntos."""
    context = {**request.model_dump(mode="json"), "project_metadata": metadata.model_dump()}
    return _render("session_estimation", version, context)


def render_metadata_extraction_prompt(
    metadata: ProjectMetadata,
    user_message: str,
    estimation: str,
    version: str = DEFAULT_PROMPT_VERSION,
) -> tuple[str, str]:
    """Renderiza el prompt del extractor que actualiza `ProjectMetadata` tras cada turno."""
    context = {
        "known_facts": metadata.model_dump_json(),
        "user_message": user_message,
        "estimation": estimation,
    }
    return _render("metadata_extraction", version, context)
