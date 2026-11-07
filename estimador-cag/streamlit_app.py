import os

import httpx
import streamlit as st

from app.schemas import MAX_TRANSCRIPT_CHARS, DetailLevel, OutputFormat, ProjectType

API_URL = os.getenv("ESTIMATOR_API_URL", "http://127.0.0.1:8000").rstrip("/")
SESSIONS_ENDPOINT = f"{API_URL}/api/v1/sessions"
REQUEST_TIMEOUT_SECONDS = 180.0  # cada turno hace dos llamadas al LLM: estimación y extractor

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


def turn_form_parts(
    transcript: str,
    project_type: ProjectType,
    detail_level: DetailLevel,
    output_format: OutputFormat,
    uploads: list,
) -> tuple[dict[str, str], list | None]:
    """Campos y archivos del multipart/form-data de un turno (`files` es None si no hay)."""
    data = {
        "transcript": transcript,
        "project_type": project_type.value,
        "detail_level": detail_level.value,
        "output_format": output_format.value,
    }
    files = [
        ("attachments", (upload.name, upload.getvalue(), upload.type or "application/octet-stream"))
        for upload in uploads
    ]
    return data, files or None


def start_session() -> bool:
    """Crea una sesión en el servicio y empieza una conversación vacía."""
    try:
        response = httpx.post(SESSIONS_ENDPOINT, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        st.session_state.session_id = response.json()["session_id"]
    except (httpx.HTTPError, KeyError, ValueError):
        st.session_state.pop("session_id", None)
        return False
    finally:
        st.session_state.conversation = []
        st.session_state.project_metadata = {}
    return True


def error_detail(response: httpx.Response) -> str:
    try:
        detail = response.json()["detail"]
    except (ValueError, KeyError, TypeError):
        return response.text
    if isinstance(detail, list):
        return "; ".join(f"{'.'.join(map(str, item['loc']))}: {item['msg']}" for item in detail)
    return str(detail)


def render_conversation() -> None:
    for message in st.session_state.conversation:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("attachments"):
                st.caption("📎 " + ", ".join(message["attachments"]))


def render_project_metadata() -> None:
    metadata = st.session_state.project_metadata
    st.subheader("Memoria del proyecto")
    if not any(metadata.values()):
        st.caption("Aún no hay datos del proyecto.")
        return
    if metadata.get("project_name"):
        st.markdown(f"**Proyecto:** {metadata['project_name']}")
    if metadata.get("assumed_team_size"):
        st.markdown(f"**Equipo asumido:** {metadata['assumed_team_size']} personas")
    if metadata.get("mentioned_technologies"):
        st.markdown(f"**Tecnologías:** {', '.join(metadata['mentioned_technologies'])}")
    if metadata.get("agreed_scope"):
        st.markdown(f"**Alcance acordado:** {metadata['agreed_scope']}")


def send_turn(transcript: str, uploads: list, params: tuple) -> None:
    data, files = turn_form_parts(transcript, *params, uploads)
    try:
        with st.spinner("Generando estimación…"):
            response = httpx.post(
                f"{SESSIONS_ENDPOINT}/{st.session_state.session_id}/estimate",
                data=data,
                files=files,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            result = response.json()
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 404:
            # El servicio guarda las sesiones en memoria: un reinicio las borra.
            start_session()
            st.warning(
                "La sesión caducó (el servicio se reinició), así que empieza una conversación "
                "nueva. Vuelve a enviar tu mensaje."
            )
        else:
            st.error(
                f"El servicio respondió {error.response.status_code}: {error_detail(error.response)}"
            )
    except httpx.RequestError as error:
        st.error(f"No se pudo conectar con el servicio en {API_URL}: {error}")
    else:
        st.session_state.conversation += [
            {
                "role": "user",
                "content": transcript,
                "attachments": [upload.name for upload in uploads],
            },
            {"role": "assistant", "content": result["text"]},
        ]
        st.session_state.project_metadata = result["project_metadata"]


def main() -> None:
    st.set_page_config(page_title="Estimador CAG", page_icon="📐")
    st.title("📐 Estimador CAG")
    st.caption(
        "Conversa con el estimador: cada mensaje afina la estimación del proyecto en curso."
    )

    if "session_id" not in st.session_state and not start_session():
        st.error(
            f"No se pudo conectar con el servicio en {API_URL}. "
            "Comprueba que está en marcha y recarga la página."
        )
        st.stop()

    with st.sidebar:
        st.header("Parámetros")
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
            key="detail_level",
        )
        output_format = st.selectbox(
            "Formato de salida",
            options=list(OutputFormat),
            format_func=OUTPUT_FORMAT_LABELS.__getitem__,
            key="output_format",
        )

    # El contenedor se declara aquí para quedar encima del formulario, pero se rellena
    # después de procesar el envío, así el mensaje nuevo aparece en la misma pasada.
    conversation_box = st.container()

    with st.form("turn_form", clear_on_submit=True):
        transcript = st.text_area(
            "Transcripción o mensaje",
            key="transcript",
            height=150,
            max_chars=MAX_TRANSCRIPT_CHARS,
            placeholder="Pega la transcripción de la reunión o añade información nueva…",
        )
        uploads = st.file_uploader(
            "Adjuntos (PDF o Word .docx)",
            type=["pdf", "docx"],
            accept_multiple_files=True,
            key="uploads",
        )
        submitted = st.form_submit_button("Enviar", type="primary", key="send")

    if submitted:
        if transcript.strip():
            send_turn(transcript.strip(), uploads, (project_type, detail_level, output_format))
        else:
            st.error("Escribe una transcripción o un mensaje.")

    with conversation_box:
        render_conversation()

    with st.sidebar:
        st.divider()
        render_project_metadata()
        st.caption(f"Sesión `{st.session_state.session_id}`")
        st.button("Nueva conversación", key="new_conversation", on_click=start_session)


if __name__ == "__main__":
    main()
