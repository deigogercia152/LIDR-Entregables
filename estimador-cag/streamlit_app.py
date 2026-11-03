import math
import os
import time

import httpx
import pandas as pd
import streamlit as st
from pydantic import ValidationError

from app.prompts.loader import DEFAULT_PROMPT_VERSION, available_versions
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
REFERENCE_COLUMNS = {
    "name": "Proyecto",
    "summary": "Qué incluía",
    "actual_hours": "Horas reales",
}


def _is_blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return isinstance(value, str) and not value.strip()


def reference_rows(rows: list[dict]) -> list[dict] | None:
    """Limpia las filas de la tabla de referencias: quita celdas y filas vacías.

    Devuelve None si no queda ninguna fila, para no enviar el campo.
    La validación de cada fila la hace `EstimationRequest`.
    """
    cleaned = [{key: value for key, value in row.items() if not _is_blank(value)} for row in rows]
    cleaned = [row for row in cleaned if row]
    return cleaned or None


def validation_messages(error: ValidationError) -> list[str]:
    messages = []
    for item in error.errors():
        loc = item["loc"]
        if loc == ("description",):
            messages.append("La descripción debe tener entre 20 y 2000 caracteres.")
        elif loc[0] == "reference_projects" and len(loc) == 3:
            column = REFERENCE_COLUMNS.get(loc[2], loc[2])
            messages.append(f"Proyecto de referencia {loc[1] + 1}, «{column}»: {item['msg']}")
        else:
            messages.append(f"{'.'.join(map(str, loc))}: {item['msg']}")
    return messages


def request_estimation(request: EstimationRequest, prompt_version: str) -> EstimationResponse:
    """Envía la petición tipada al servicio IA y valida su respuesta."""
    response = httpx.post(
        ESTIMATE_ENDPOINT,
        params={"prompt_version": prompt_version},
        json=request.model_dump(mode="json", exclude_none=True),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return EstimationResponse.model_validate(response.json())


def main() -> None:
    st.set_page_config(page_title="Estimador CAG", page_icon="📐")
    st.title("📐 Estimador CAG")
    st.caption("Describe el proyecto, elige los parámetros y obtén una estimación.")

    if "last_result" not in st.session_state:
        st.session_state.last_result = None

    versions = available_versions()
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
        with st.expander("Proyectos de referencia (opcional)"):
            st.caption("Proyectos parecidos ya entregados, con sus horas reales. Máximo 5.")
            references = st.data_editor(
                pd.DataFrame(columns=list(REFERENCE_COLUMNS)).astype(
                    {"name": "string", "summary": "string", "actual_hours": "Int64"}
                ),
                key="reference_projects",
                num_rows="dynamic",
                width="stretch",
                column_config={
                    "name": st.column_config.TextColumn(REFERENCE_COLUMNS["name"], max_chars=100),
                    "summary": st.column_config.TextColumn(
                        REFERENCE_COLUMNS["summary"], max_chars=500
                    ),
                    "actual_hours": st.column_config.NumberColumn(
                        REFERENCE_COLUMNS["actual_hours"], min_value=1, step=1
                    ),
                },
            )
        prompt_version = st.selectbox(
            "Versión del prompt",
            options=versions,
            index=versions.index(DEFAULT_PROMPT_VERSION),
            key="prompt_version",
        )
        submitted = st.form_submit_button("Estimar", type="primary")

    if submitted:
        try:
            estimation_request = EstimationRequest(
                description=description,
                project_type=project_type,
                detail_level=detail_level,
                output_format=output_format,
                reference_projects=reference_rows(references.to_dict("records")),
            )
        except ValidationError as error:
            for message in validation_messages(error):
                st.error(message)
        else:
            try:
                with st.spinner("Generando estimación…"):
                    start = time.perf_counter()
                    estimation = request_estimation(estimation_request, prompt_version)
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


if __name__ == "__main__":
    main()
