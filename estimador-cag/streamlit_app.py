import os
import time

import httpx
import streamlit as st
from pydantic import ValidationError

from app.schemas import (
    DetailLevel,
    EstimationRequest,
    EstimationResponse,
    OutputFormat,
    ProjectType,
)

API_URL = os.getenv("ESTIMATOR_API_URL", "http://127.0.0.1:8000").rstrip("/")
ESTIMATE_ENDPOINT = f"{API_URL}/api/v1/estimate"
REQUEST_TIMEOUT_SECONDS = 120.0

PROJECT_TYPE_LABELS = {
    ProjectType.MOBILE_APP: "App móvil",
    ProjectType.WEB_SAAS: "Web / SaaS",
    ProjectType.INTERNAL_TOOL: "Herramienta interna",
    ProjectType.DATA_PIPELINE: "Pipeline de datos",
}
DETAIL_LEVEL_LABELS = {
    DetailLevel.SUMMARY: "Resumen",
    DetailLevel.MEDIUM: "Medio",
    DetailLevel.DETAILED: "Detallado",
}
OUTPUT_FORMAT_LABELS = {
    OutputFormat.PHASES_TABLE: "Tabla por fases",
    OutputFormat.LINE_ITEMS: "Lista de partidas",
    OutputFormat.NARRATIVE: "Narrativa",
}


def validation_messages(error: ValidationError) -> list[str]:
    messages = []
    for item in error.errors():
        if item["loc"] == ("description",):
            messages.append("La descripción debe tener entre 20 y 2000 caracteres.")
        else:
            messages.append(f"{'.'.join(map(str, item['loc']))}: {item['msg']}")
    return messages


def request_estimation(request: EstimationRequest) -> EstimationResponse:
    """Envía la petición tipada al servicio IA y valida su respuesta."""
    response = httpx.post(
        ESTIMATE_ENDPOINT,
        json=request.model_dump(mode="json"),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return EstimationResponse.model_validate(response.json())


st.set_page_config(page_title="Estimador CAG", page_icon="📐")
st.title("📐 Estimador CAG")
st.caption("Describe el proyecto, elige los parámetros y obtén una estimación.")

if "last_result" not in st.session_state:
    st.session_state.last_result = None

with st.form("estimation_form"):
    description = st.text_area(
        "Descripción del proyecto",
        key="description",
        height=200,
        max_chars=2000,
        placeholder="Qué necesita el cliente, usuarios, integraciones, plazos…",
    )
    project_type = st.selectbox(
        "Tipo de proyecto",
        options=list(ProjectType),
        format_func=PROJECT_TYPE_LABELS.__getitem__,
        key="project_type",
    )
    detail_level = st.radio(
        "Nivel de detalle",
        options=list(DetailLevel),
        index=1,
        format_func=DETAIL_LEVEL_LABELS.__getitem__,
        horizontal=True,
        key="detail_level",
    )
    output_format = st.selectbox(
        "Formato de salida",
        options=list(OutputFormat),
        format_func=OUTPUT_FORMAT_LABELS.__getitem__,
        key="output_format",
    )
    submitted = st.form_submit_button("Estimar", type="primary")

if submitted:
    try:
        estimation_request = EstimationRequest(
            description=description,
            project_type=project_type,
            detail_level=detail_level,
            output_format=output_format,
        )
    except ValidationError as error:
        for message in validation_messages(error):
            st.error(message)
    else:
        try:
            with st.spinner("Generando estimación…"):
                start = time.perf_counter()
                estimation = request_estimation(estimation_request)
                elapsed = time.perf_counter() - start
        except httpx.HTTPStatusError as error:
            st.error(
                f"El servicio respondió {error.response.status_code}: {error.response.text}"
            )
        except httpx.RequestError as error:
            st.error(f"No se pudo conectar con el servicio en {API_URL}: {error}")
        except ValidationError:
            st.error("El servicio devolvió una respuesta con un formato inesperado.")
        else:
            st.session_state.last_result = {
                "text": estimation.text,
                "prompt_version": estimation.prompt_version,
                "elapsed": elapsed,
            }

result = st.session_state.last_result
if result is not None:
    st.divider()
    st.markdown(result["text"])
    st.caption(f"Prompt {result['prompt_version']} · {result['elapsed']:.1f} s")

with st.sidebar:
    st.header("Servicio IA")
    st.code(ESTIMATE_ENDPOINT, language=None)
    st.caption("Configurable con la variable de entorno `ESTIMATOR_API_URL`.")
