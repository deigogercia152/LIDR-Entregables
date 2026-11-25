import math

import openai
import pytest

from scripts import compare


def test_cosine_similarity_of_known_vectors() -> None:
    assert compare.cosine_similarity([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)
    assert compare.cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)
    assert compare.cosine_similarity([1, 0], [-1, 0]) == pytest.approx(-1.0)
    assert compare.cosine_similarity([1, 1], [1, 0]) == pytest.approx(1 / math.sqrt(2))


def test_cosine_similarity_ignores_vector_magnitude() -> None:
    assert compare.cosine_similarity([1, 2], [10, 20]) == pytest.approx(1.0)


@pytest.mark.parametrize("a, b", [([0, 0], [1, 1]), ([1, 1], [1])])
def test_cosine_similarity_rejects_zero_norm_and_mismatched_vectors(a, b) -> None:
    with pytest.raises(ValueError):
        compare.cosine_similarity(a, b)


class FakeEmbedder:
    vectors = {"alpha": [1.0, 0.0], "beta": [1.0, 1.0]}

    def embed_one(self, text: str) -> list[float]:
        return self.vectors[text]


def test_cli_prints_both_texts_and_the_similarity(capsys) -> None:
    code = compare.main(["--text-a", "alpha", "--text-b", "beta"], embedder=FakeEmbedder())

    assert code == 0
    assert capsys.readouterr().out.splitlines() == [
        "Text A: alpha",
        "Text B: beta",
        "Cosine similarity: 0.7071",
    ]


def test_cli_fails_with_a_clear_message_when_there_is_no_api_key(monkeypatch, capsys) -> None:
    monkeypatch.setattr(compare.settings, "openai_api_key", None)

    code = compare.main(["--text-a", "a", "--text-b", "b"])

    assert code == 1
    assert "OPENAI_API_KEY" in capsys.readouterr().err


def test_cli_reports_an_api_error_without_a_traceback(capsys) -> None:
    class FailingEmbedder:
        def embed_one(self, text: str) -> list[float]:
            raise openai.OpenAIError("input cannot be an empty string")

    code = compare.main(["--text-a", "", "--text-b", "x"], embedder=FailingEmbedder())

    captured = capsys.readouterr()
    assert code == 1
    assert "input cannot be an empty string" in captured.err
    assert captured.out == ""
