import os
import time

import streamlit as st

SECRET_KEYS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LLM_PROVIDER", "LLM_MODEL")


def load_streamlit_secrets() -> None:
    """Copia los secretos de st.secrets a variables de entorno, si existen.

    Debe ejecutarse antes de importar `app.config`: pydantic-settings da prioridad
    a las variables de entorno sobre `.env`, y `setdefault` respeta las ya definidas.
    """
    try:
        for key in SECRET_KEYS:
            if key in st.secrets:
                os.environ.setdefault(key, str(st.secrets[key]))
    except Exception:
        # Sin secrets.toml: la configuración se lee de `.env`.
        pass


load_streamlit_secrets()

from app.config import settings  # noqa: E402
from app.context.examples import get_estimation_examples  # noqa: E402
from app.services.llm_services import build_system_message, stream_estimation  # noqa: E402


def render_sidebar() -> None:
    with st.sidebar:
        st.header("Contexto CAG")

        st.subheader("System prompt activo")
        st.text_area(
            "System prompt",
            value=build_system_message(),
            height=300,
            disabled=True,
            label_visibility="collapsed",
        )

        st.subheader("Estimaciones de ejemplo")
        for index, example in enumerate(get_estimation_examples(), start=1):
            with st.expander(f"Ejemplo {index}"):
                st.markdown(f"**Resumen de la reunión:** {example['meeting_summary'].strip()}")
                st.code(example["estimation"].strip(), language="markdown")

        st.subheader("Última llamada")
        metrics = st.session_state.last_metrics
        if metrics is None:
            st.caption("Aún no se ha generado ninguna estimación.")
        else:
            st.metric("Modelo", metrics["model"])
            col_in, col_out = st.columns(2)
            col_in.metric("Tokens entrada", metrics["input_tokens"])
            col_out.metric("Tokens salida", metrics["output_tokens"])
            st.metric("Tiempo de respuesta", f"{metrics['elapsed']:.2f} s")

        if st.button("Nueva conversación", width="stretch"):
            st.session_state.messages = []
            st.session_state.last_metrics = None
            st.rerun()


st.set_page_config(page_title="Estimador CAG", page_icon="📐")
st.title("📐 Estimador CAG")
st.caption(
    f"Pega la transcripción de una reunión y obtén una estimación del proyecto · "
    f"{settings.llm_provider} / {settings.llm_model}"
)

if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_metrics" not in st.session_state:
    st.session_state.last_metrics = None

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Pega aquí la transcripción de la reunión…"):
    transcription = prompt.strip()
    if not transcription:
        st.warning("La transcripción no puede estar vacía.")
    else:
        st.session_state.messages.append({"role": "user", "content": transcription})
        with st.chat_message("user"):
            st.markdown(transcription)

        with st.chat_message("assistant"):
            try:
                start = time.perf_counter()
                provider, stream = stream_estimation(transcription)
                estimation = st.write_stream(stream)
                elapsed = time.perf_counter() - start
            except Exception as error:
                st.error(f"No se pudo generar la estimación: {error}")
            else:
                st.session_state.messages.append({"role": "assistant", "content": estimation})
                usage = provider.last_usage
                st.session_state.last_metrics = {
                    "model": usage.model if usage else settings.llm_model,
                    "input_tokens": usage.input_tokens if usage else "—",
                    "output_tokens": usage.output_tokens if usage else "—",
                    "elapsed": elapsed,
                }

# El sidebar se pinta al final para que las métricas reflejen la llamada recién hecha.
render_sidebar()
