import io

from pypdf import PdfReader

from evals.stress.fixtures.build_pdfs import CANARIES, build_pdf
from evals.stress.scenarios import CHECKPOINTS, MAX_TURNS, SCENARIOS


def test_every_scenario_has_consecutive_turns_up_to_the_maximum() -> None:
    assert set(SCENARIOS) == {"growing", "pivot", "contradiction"}
    for scenario in SCENARIOS.values():
        assert [turn[0] for turn in scenario.turns] == list(range(1, MAX_TURNS + 1))
        assert max(CHECKPOINTS) == MAX_TURNS


def test_prefixes_and_declared_facts_follow_the_turn_index() -> None:
    contradiction = SCENARIOS["contradiction"]

    assert len(contradiction.turns_up_to(6)) == 6
    assert contradiction.facts_declared_before(3) == ["Nimbus"]
    assert contradiction.facts_declared_before(9) == ["Nimbus", "30000", "80000"]


def test_pivot_and_contradiction_declare_what_gets_superseded() -> None:
    assert SCENARIOS["pivot"].superseded == {"React": 5}
    assert SCENARIOS["contradiction"].superseded == {"30000": 8}


def test_pdf_fixture_is_deterministic_extractable_and_carries_the_three_canaries() -> None:
    first, second = build_pdf(5), build_pdf(5)
    text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(first)).pages)

    assert first == second
    assert all(canary in text for canary in CANARIES.values())
    assert 5000 <= len(text) <= 6000
