import pytest
from jinja2 import UndefinedError

from app.prompts import loader
from app.prompts.loader import render_estimation_prompt
from app.schemas import DetailLevel, EstimationRequest, OutputFormat, ProjectType

DESCRIPTION = "Necesitamos una app móvil para que los socios reserven pistas de pádel."


def make_request(**overrides) -> EstimationRequest:
    fields = {
        "description": DESCRIPTION,
        "project_type": ProjectType.MOBILE_APP,
        "detail_level": DetailLevel.MEDIUM,
        "output_format": OutputFormat.LINE_ITEMS,
    }
    fields.update(overrides)
    return EstimationRequest(**fields)


def test_user_prompt_wraps_description_in_project_description_block() -> None:
    _, user = render_estimation_prompt(make_request())

    assert f"<project_description>\n{DESCRIPTION}\n</project_description>" in user
    assert "mobile_app" in user


def test_phases_table_format_instructions_only_when_requested() -> None:
    table_system, _ = render_estimation_prompt(
        make_request(output_format=OutputFormat.PHASES_TABLE)
    )
    narrative_system, _ = render_estimation_prompt(
        make_request(output_format=OutputFormat.NARRATIVE)
    )

    assert "phases_table" in table_system
    assert "confidence_pct" in table_system
    assert "phases_table" not in narrative_system
    assert "confidence_pct" not in narrative_system


def test_detailed_level_asks_for_assumptions_per_phase_and_summary_does_not() -> None:
    detailed_system, _ = render_estimation_prompt(
        make_request(detail_level=DetailLevel.DETAILED)
    )
    summary_system, _ = render_estimation_prompt(
        make_request(detail_level=DetailLevel.SUMMARY)
    )

    assert "asunciones por fase" in detailed_system
    assert "asunciones por fase" not in summary_system


def test_system_prompt_includes_few_shot_examples() -> None:
    system, user = render_estimation_prompt(make_request())

    assert "<examples>" in system
    assert system.count("<example>") >= 2
    assert DESCRIPTION not in system
    assert "<examples>" not in user


def test_default_version_is_v1() -> None:
    assert loader.DEFAULT_PROMPT_VERSION == "v1"
    assert render_estimation_prompt(make_request()) == render_estimation_prompt(
        make_request(), version="v1"
    )


@pytest.mark.parametrize("version", ["v999", "../estimation", ""])
def test_unknown_version_is_rejected(version: str) -> None:
    with pytest.raises(ValueError, match="Versión de prompt desconocida"):
        render_estimation_prompt(make_request(), version=version)


def test_missing_template_variable_fails_loudly() -> None:
    template = loader._get_environment("v1").from_string("{{ not_provided }}")

    with pytest.raises(UndefinedError):
        template.render()
