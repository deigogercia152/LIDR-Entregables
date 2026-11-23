import tiktoken

from app.embedding_pipeline.chunker import JSONStructuralChunker
from app.embedding_pipeline.schemas import Budget


def chunk_budgets(*payloads: dict):
    return JSONStructuralChunker().chunk([Budget(**payload) for payload in payloads])


def test_one_component_is_one_chunk_with_a_traceable_id(make_budget_payload, component_payload) -> None:
    second = {**component_payload, "component_id": "TXN-002", "name": "Transaction history API"}

    chunks = chunk_budgets(make_budget_payload(components=[component_payload, second]))

    assert [chunk.chunk_id for chunk in chunks] == ["BUD-2024-014::AUTH-001", "BUD-2024-014::TXN-002"]


def test_chunk_text_prepends_the_parent_context_to_the_component_details(
    make_budget_payload,
) -> None:
    (chunk,) = chunk_budgets(make_budget_payload())

    assert chunk.text == (
        "[Project: Mobile banking API with OAuth 2.0 authentication and PSD2 compliance]\n"
        "[Client sector: finance | Year: 2024 | Main tech: ruby_on_rails]\n"
        "\n"
        "Component: OAuth 2.0 authentication backend\n"
        "Description: Implementation of OAuth 2.0 flows with JWT-based session management.\n"
        "Tech stack: ruby_on_rails, postgresql, redis\n"
        "Complexity: high\n"
        "Estimated hours: 120"
    )


def test_metadata_carries_the_filterable_fields_but_none_of_them_is_embedded_by_name(
    make_budget_payload,
) -> None:
    (chunk,) = chunk_budgets(make_budget_payload())

    assert chunk.metadata == {
        "budget_id": "BUD-2024-014",
        "component_id": "AUTH-001",
        "client_sector": "finance",
        "main_technology": "ruby_on_rails",
        "year": 2024,
        "complexity": "high",
        "estimated_hours": 120,
    }
    assert "client_sector" not in chunk.text


def test_token_count_uses_the_embedding_model_tokenizer(make_budget_payload) -> None:
    (chunk,) = chunk_budgets(make_budget_payload())

    encoding = tiktoken.encoding_for_model("text-embedding-3-small")
    assert chunk.token_count == len(encoding.encode(chunk.text))
    assert chunk.token_count > 0


def test_a_long_description_stays_in_a_single_chunk_with_no_splitting(
    make_budget_payload, component_payload
) -> None:
    component_payload["description"] = "Detailed requirement sentence. " * 300

    (chunk,) = chunk_budgets(make_budget_payload(components=[component_payload]))

    assert chunk.text.count("Detailed requirement sentence.") == 300
    assert chunk.token_count > 1000


def test_text_that_looks_like_a_special_token_does_not_break_the_count(
    make_budget_payload, component_payload
) -> None:
    component_payload["description"] = "Parse <|endoftext|> markers in uploaded files"

    (chunk,) = chunk_budgets(make_budget_payload(components=[component_payload]))

    assert chunk.token_count > 0


def test_several_budgets_are_chunked_in_order(make_budget_payload) -> None:
    chunks = chunk_budgets(make_budget_payload("BUD-A"), make_budget_payload("BUD-B"))

    assert [chunk.chunk_id for chunk in chunks] == ["BUD-A::AUTH-001", "BUD-B::AUTH-001"]
