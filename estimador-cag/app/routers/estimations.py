from fastapi import APIRouter, HTTPException

from app.prompts.loader import DEFAULT_PROMPT_VERSION, render_estimation_prompt
from app.schemas import EstimationRequest, EstimationResponse
from app.services.llm_services import get_llm_provider

router = APIRouter()


@router.post("/estimate", response_model=EstimationResponse)
def estimate(request: EstimationRequest) -> EstimationResponse:
    system, user = render_estimation_prompt(request, version=DEFAULT_PROMPT_VERSION)
    try:
        provider = get_llm_provider()
    except ValueError as error:
        # Configuración incompleta (p. ej. falta la API key): no es culpa del cliente.
        raise HTTPException(status_code=503, detail=str(error)) from error
    text = provider.process_message(system, user)
    return EstimationResponse(text=text, prompt_version=DEFAULT_PROMPT_VERSION)
