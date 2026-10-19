from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from app.config import settings
from app.services.llm_services import process_estimation_request

router = APIRouter()


class EstimationRequest(BaseModel):
    transcription: str = Field(
        min_length=1,
        description="Transcripción de la reunión con el cliente.",
    )

    @field_validator("transcription")
    @classmethod
    def transcription_must_not_be_blank(cls, value: str) -> str:
        transcription = value.strip()
        if not transcription:
            raise ValueError("La transcripción no puede estar vacía.")
        return transcription


class EstimationResponse(BaseModel):
    estimation: str
    model: str
    provider: Literal["openai", "anthropic"]


@router.post("/estimate", response_model=EstimationResponse)
def estimate(request: EstimationRequest) -> EstimationResponse:
    estimation = process_estimation_request(request.transcription)
    return EstimationResponse(
        estimation=estimation,
        model=settings.llm_model,
        provider=settings.llm_provider,
    )
