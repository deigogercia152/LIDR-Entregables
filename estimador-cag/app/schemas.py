from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ProjectType(str, Enum):
    MOBILE_APP = "mobile_app"
    WEB_SAAS = "web_saas"
    INTERNAL_TOOL = "internal_tool"
    DATA_PIPELINE = "data_pipeline"


class DetailLevel(str, Enum):
    SUMMARY = "summary"
    MEDIUM = "medium"
    DETAILED = "detailed"


class OutputFormat(str, Enum):
    PHASES_TABLE = "phases_table"
    LINE_ITEMS = "line_items"
    NARRATIVE = "narrative"


class ReferenceProject(BaseModel):
    """Proyecto ya entregado cuyo esfuerzo real sirve de referencia al modelo."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=500)
    actual_hours: int = Field(gt=0, le=100_000)


class EstimationRequest(BaseModel):
    # Se quitan los espacios de los extremos antes de comprobar la longitud,
    # así una descripción hecha solo de espacios no llega al modelo.
    model_config = ConfigDict(str_strip_whitespace=True)

    description: str = Field(min_length=20, max_length=2000)
    project_type: ProjectType
    detail_level: DetailLevel
    output_format: OutputFormat
    reference_projects: list[ReferenceProject] | None = Field(default=None, max_length=5)


class EstimationResponse(BaseModel):
    text: str
    prompt_version: str
