import pytest
from structlog.testing import capture_logs

from app.prompts.loader import available_versions, render_estimation_prompt
from app.schemas import (
    DetailLevel,
    EstimationRequest,
    OutputFormat,
    ProjectType,
    ReferenceProject,
)

DESCRIPTION = "Un panel interno para que el equipo de soporte gestione devoluciones."
REFERENCE = ReferenceProject(
    name="Portal de incidencias",
    summary="Panel interno con roles y exportación a CSV",
    actual_hours=140,
)


def make_request(**overrides) -> EstimationRequest:
    fields = {
        "description": DESCRIPTION,
        "project_type": ProjectType.INTERNAL_TOOL,
        "detail_level": DetailLevel.MEDIUM,
        "output_format": OutputFormat.LINE_ITEMS,
    }
    fields.update(overrides)
    return EstimationRequest(**fields)


def test_v1_and_v2_are_available() -> None:
    assert {"v1", "v2"} <= set(available_versions())


def test_v2_is_a_deliberate_variation_of_v1() -> None:
    v1_system, _ = render_estimation_prompt(make_request(), version="v1")
    v2_system, _ = render_estimation_prompt(make_request(), version="v2")

    assert v1_system != v2_system
    assert "cliente no técnico" in v2_system
    assert "cliente no técnico" not in v1_system


@pytest.mark.parametrize("version", available_versions())
def test_every_version_keeps_the_template_contract(version: str) -> None:
    _, user = render_estimation_prompt(make_request(), version=version)
    table_system, _ = render_estimation_prompt(
        make_request(output_format=OutputFormat.PHASES_TABLE), version=version
    )
    narrative_system, _ = render_estimation_prompt(
        make_request(output_format=OutputFormat.NARRATIVE), version=version
    )
    detailed_system, _ = render_estimation_prompt(
        make_request(detail_level=DetailLevel.DETAILED), version=version
    )
    summary_system, _ = render_estimation_prompt(
        make_request(detail_level=DetailLevel.SUMMARY), version=version
    )

    assert f"<project_description>\n{DESCRIPTION}\n</project_description>" in user
    assert "confidence_pct" in table_system
    assert "confidence_pct" not in narrative_system
    assert "asunciones por fase" in detailed_system
    assert "asunciones por fase" not in summary_system


@pytest.mark.parametrize("version", available_versions())
def test_reference_projects_are_listed_when_present(version: str) -> None:
    other = ReferenceProject(name="App de fichajes", summary="App móvil con GPS", actual_hours=260)
    _, user = render_estimation_prompt(
        make_request(reference_projects=[REFERENCE, other]), version=version
    )

    assert "<reference_projects>" in user
    assert "- Portal de incidencias: Panel interno con roles y exportación a CSV (140 h reales)" in user
    assert "- App de fichajes: App móvil con GPS (260 h reales)" in user


@pytest.mark.parametrize("reference_projects", [None, []])
def test_reference_projects_block_is_omitted_when_absent(reference_projects) -> None:
    _, user = render_estimation_prompt(make_request(reference_projects=reference_projects))

    assert "reference_projects" not in user


def test_render_logs_version_and_content_hash_without_the_description() -> None:
    with capture_logs() as logs:
        render_estimation_prompt(make_request(), version="v2")
        render_estimation_prompt(make_request(), version="v2")
        render_estimation_prompt(make_request(description=DESCRIPTION + " Con app móvil."))

    assert [log["event"] for log in logs] == ["prompt_rendered"] * 3
    assert [log["prompt_version"] for log in logs] == ["v2", "v2", "v1"]
    assert logs[0]["prompt_hash"] == logs[1]["prompt_hash"]
    assert logs[0]["prompt_hash"] != logs[2]["prompt_hash"]
    assert len(logs[0]["prompt_hash"]) == 16
    assert DESCRIPTION not in str(logs)
