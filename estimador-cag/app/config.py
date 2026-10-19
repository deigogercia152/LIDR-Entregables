from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    llm_provider: Literal["openai", "anthropic"] = "openai"
    llm_model: str = Field(default="gpt-4o-mini", min_length=1)
    app_env: str = "development"
    log_level: str = "INFO"

    @field_validator("llm_model")
    @classmethod
    def llm_model_must_not_be_blank(cls, value: str) -> str:
        model = value.strip()
        if not model:
            raise ValueError("LLM_MODEL debe contener el nombre explícito del modelo.")
        return model


settings = Settings()