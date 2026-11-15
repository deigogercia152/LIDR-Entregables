import structlog

from app.prompts.loader import render_metadata_extraction_prompt, render_session_prompt
from app.schemas import SessionEstimationRequest, TurnObservation
from app.services.llm_wrapper import ObservedProvider
from app.services.providers.i_llm_provider import ILLMProvider
from app.sessions import ProjectMetadata, Session

logger = structlog.get_logger(__name__)


def run_turn(session: Session, request: SessionEstimationRequest, provider: ILLMProvider) -> str:
    """Ejecuta un turno: estima con historial + memoria y actualiza ambos.

    El llamador debe tener `session.lock`. El turno solo se guarda si el LLM responde:
    si falla, la sesión queda como estaba y el cliente puede reintentar.
    """
    observed = ObservedProvider(provider)
    system, user = render_session_prompt(request, session.metadata)
    estimation = observed.process_chat(system, session.history.chat_messages(user))
    session.history.add_turn(user, estimation)
    session.turn_count += 1
    session.metadata = _updated_metadata(session.metadata, user, estimation, observed)
    session.last_observation = _observe_turn(session, user, request, observed)
    return estimation


def _observe_turn(
    session: Session, user: str, request: SessionEstimationRequest, observed: ObservedProvider
) -> TurnObservation:
    """Agrega en un único evento `turn_observed` lo que antes eran logs sueltos.

    Un evento por turno permite volcar un CSV de una pasada y correlacionar
    `messages_in_window` con `cost_usd` sin reconciliar marcas de tiempo.
    """
    observation = TurnObservation(
        turn_index=session.turn_count,
        session_id=session.id,
        enriched_transcript_chars=len(user),
        attachments_total_chars=sum(len(attachment.text) for attachment in request.attachments),
        messages_in_window=len(session.history.chat_messages()),
        anchors_count=0,  # sin anclas en este servicio
        summary_chars=0,  # sin summarizer en este servicio
        tokens_in=observed.tokens_in,
        tokens_out=observed.tokens_out,
        cost_usd=observed.cost_usd,
        latency_ms=observed.latency_ms,
        cache_hit_kind="none",  # sin caches en este servicio
        last_resolved_tier="n/a",  # sin tier dinámico en este servicio
        llm_calls=len(observed.calls),
    )
    logger.info("turn_observed", **observation.model_dump())
    return observation


def _updated_metadata(
    current: ProjectMetadata, user_message: str, estimation: str, provider: ILLMProvider
) -> ProjectMetadata:
    """Segunda llamada al LLM que extrae los hechos del proyecto de este turno.

    Es best-effort: la estimación ya está hecha, así que si el extractor falla o
    devuelve algo que no es el JSON esperado se conserva la memoria anterior.
    """
    system, user = render_metadata_extraction_prompt(current, user_message, estimation)
    try:
        return current.merged_with(_parse_metadata(provider.process_message(system, user)))
    except Exception:  # noqa: BLE001 - cualquier fallo del extractor (red, JSON, schema) se tolera
        logger.warning("metadata_extraction_failed", exc_info=True)
        return current


def _parse_metadata(raw: str) -> ProjectMetadata:
    # El extractor es un LLM: puede envolver el JSON en texto o en un bloque de código.
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end < start:
        raise ValueError("la respuesta del extractor no contiene un objeto JSON")
    return ProjectMetadata.model_validate_json(raw[start : end + 1])
