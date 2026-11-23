import copy

import pytest

COMPONENT = {
    "component_id": "AUTH-001",
    "name": "OAuth 2.0 authentication backend",
    "description": "Implementation of OAuth 2.0 flows with JWT-based session management.",
    "tech_stack": ["ruby_on_rails", "postgresql", "redis"],
    "estimated_hours": 120,
    "complexity": "high",
    "dependencies": [],
}


def budget_payload(budget_id: str = "BUD-2024-014", components: list[dict] | None = None) -> dict:
    return {
        "budget_id": budget_id,
        "client_metadata": {"name": "FintechCorp", "sector": "finance", "country": "ES"},
        "project_summary": "Mobile banking API with OAuth 2.0 authentication and PSD2 compliance",
        "main_technology": "ruby_on_rails",
        "year": 2024,
        "total_estimated_hours": 480,
        "components": components or [copy.deepcopy(COMPONENT)],
    }


@pytest.fixture
def make_budget_payload():
    return budget_payload


@pytest.fixture
def component_payload():
    return copy.deepcopy(COMPONENT)
