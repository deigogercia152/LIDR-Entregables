from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ValidationError

from app.attachments import MAX_FILE_BYTES, AttachmentError, extract_attachments
from app.config import settings
from app.schemas import (
    DetailLevel,
    OutputFormat,
    ProjectType,
    SessionEstimationRequest,
    SessionEstimationResponse,
)
from app.services.llm_services import get_llm_provider
from app.services.session_service import run_turn
from app.sessions import SessionStore

router = APIRouter()

session_store = SessionStore(settings.max_sessions)
SESSION_PROMPT_VERSION = "v1"


class SessionCreated(BaseModel):
    session_id: str


@router.post("/sessions", response_model=SessionCreated, status_code=201)
def create_session() -> SessionCreated:
    return SessionCreated(session_id=session_store.create(settings.session_max_turns).id)


@router.post("/sessions/{session_id}/estimate", response_model=SessionEstimationResponse)
def estimate_in_session(
    session_id: str,
    transcript: Annotated[str, Form()],
    project_type: Annotated[ProjectType, Form()],
    detail_level: Annotated[DetailLevel, Form()],
    output_format: Annotated[OutputFormat, Form()],
    attachments: Annotated[list[UploadFile] | None, File()] = None,
) -> SessionEstimationResponse:
    session = session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada: crea una con POST /sessions.")

    # Se lee un byte de más para detectar archivos que superan el límite sin cargarlos enteros.
    files = [
        (upload.filename, upload.file.read(MAX_FILE_BYTES + 1))
        for upload in attachments or []
        if upload.filename  # los clientes mandan una parte vacía si no se eligió ningún archivo
    ]
    try:
        request = SessionEstimationRequest(
            transcript=transcript,
            project_type=project_type,
            detail_level=detail_level,
            output_format=output_format,
            attachments=extract_attachments(files),
        )
    except AttachmentError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    except ValidationError as error:
        raise HTTPException(
            status_code=422, detail=error.errors(include_url=False, include_context=False, include_input=False)
        ) from error

    try:
        provider = get_llm_provider()
    except ValueError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    with session.lock:
        text = run_turn(session, request, provider)
        return SessionEstimationResponse(
            text=text,
            prompt_version=SESSION_PROMPT_VERSION,
            session_id=session.id,
            turn=len(session.history),
            project_metadata=session.metadata,
        )
