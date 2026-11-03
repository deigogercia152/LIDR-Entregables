from app.config import settings
from app.services.providers.antropic_llm_provider import AnthropicLLMProvider
from app.services.providers.i_llm_provider import ILLMProvider
from app.services.providers.openai_llm_provider import OpenAILLMProvider


def get_llm_provider() -> ILLMProvider:
    """
    Devuelve el proveedor LLM configurado en `settings`.

    Los prompts se construyen fuera, en `app.prompts.loader`; el proveedor solo
    recibe los mensajes de sistema y de usuario ya renderizados.
    """
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
