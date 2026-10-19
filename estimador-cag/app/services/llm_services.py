from app.config import settings
from app.context.examples import get_estimation_examples
from app.services.providers.antropic_llm_provider import AnthropicLLMProvider
from app.services.providers.i_llm_provider import ILLMProvider
from app.services.providers.openai_llm_provider import OpenAILLMProvider

SYSTEM_PROMT = """
Eres un estimador de proyectos de software. 
Tu tarea es generar estimaciones de esfuerzo y recursos para proyectos de software basándote en resúmenes de reuniones con clientes. 
Debes analizar el resumen de la reunión y proporcionar una estimación detallada que incluya:
    1. Desglose de tareas: Lista de tareas necesarias para completar el proyecto, con una estimación de horas y coste para cada tarea.
    2. Total estimado: Suma total de horas y coste estimados para el proyecto. Explicita la moneda y la tarifa asumida para calcular costes.
    3. Equipo recomendado: Roles y número de personas necesarias para completar el proyecto.
    4. Duración estimada: Tiempo total estimado para completar el proyecto, basado en la disponibilidad del equipo y la complejidad del proyecto.
    Debes presentar la estimación en un formato claro y estructurado, utilizando encabezados y listas para mejorar la legibilidad. 

Asegúrate de que la estimación sea realista y basada en la información proporcionada en el resumen de la reunión. 
Evita incluir información que no esté directamente relacionada con el proyecto descrito en el resumen.
"""

def build_system_message() -> str:
    """
    Construye el mensaje de entrada para el modelo. 
    El mensaje incluye el sistem prompt, ejemplos de estimaciones y el resumen de la reunion a estimar.

    Args:
        meeting_summary (str): Resumen de la reunión con el cliente.
    """

    examples = get_estimation_examples()

    message = SYSTEM_PROMT + "\n\n"

    message += "Ejemplos de estimaciones:\n"

    for example in examples:
        message += f"Resumen de la reunión: {example['meeting_summary']}\n"
        message += f"Estimación: {example['estimation']}\n\n"

    return message

def build_user_message(meeting_summary: str) -> str:
    """
    Construye el mensaje de entrada para el modelo. El mensaje incluye el resumen de la reunion a estimar.

    Args:
        meeting_summary (str): Resumen de la reunión con el cliente.
    """

    message = f"Resumen de la reunión a estimar: {meeting_summary}\n"
    message += "Por favor, proporciona una estimación detallada basada en este resumen.\n"

    return message

def process_estimation_request(meeting_summary: str) -> str:
    """
    Procesa la solicitud de estimación. 
    Construye el mensaje de entrada para el modelo y llama al servicio LLM para obtener la estimación.

    Args:
        meeting_summary (str): Resumen de la reunión con el cliente.

    Returns:
        str: Estimación generada por el modelo.
    """

    system_message = build_system_message()
    user_message = build_user_message(meeting_summary)

    provider = _get_llm_provider()
    return provider.process_message(system_message, user_message)


def _get_llm_provider() -> ILLMProvider:
    provider_name = settings.llm_provider
    model = settings.llm_model
    if provider_name == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY no está configurada.")
        return OpenAILLMProvider(
            api_key=settings.openai_api_key,
            model=model,
        )
    if provider_name == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY no está configurada.")
        return AnthropicLLMProvider(
            api_key=settings.anthropic_api_key,
            model=model,
        )
    raise ValueError(f"Proveedor LLM no soportado: {provider_name}")
