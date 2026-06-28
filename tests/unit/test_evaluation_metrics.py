"""Tests de las métricas de evaluación (F1) con valores conocidos."""

from __future__ import annotations

from meeting_forge.evaluation.metrics import (
    match_items,
    mean_wer,
    precision_at_k,
    prf1_from_counts,
    recall_at_k,
    word_error_rate,
)
from meeting_forge.evaluation.runner import evaluate, render_markdown
from meeting_forge.evaluation.schemas import EvalDataset


class TestWER:
    def test_identical_is_zero(self) -> None:
        assert word_error_rate("hola mundo", "hola mundo") == 0.0

    def test_one_substitution_over_two_words(self) -> None:
        assert word_error_rate("hola mundo", "hola planeta") == 0.5

    def test_empty_reference(self) -> None:
        assert word_error_rate("", "") == 0.0
        assert word_error_rate("", "algo") == 1.0

    def test_mean_over_pairs(self) -> None:
        assert mean_wer([("a b", "a b"), ("a b", "a c")]) == 0.25


class TestMatchItems:
    def test_exact_match(self) -> None:
        assert match_items(["adoptar chromadb"], ["adoptar chromadb"]) == (1, 0, 0)

    def test_extra_prediction_is_false_positive(self) -> None:
        tp, fp, fn = match_items(["a b c d"], ["a b c d", "x y z"])
        assert (tp, fp, fn) == (1, 1, 0)

    def test_missing_prediction_is_false_negative(self) -> None:
        tp, fp, fn = match_items(["a b", "c d"], ["a b"])
        assert (tp, fp, fn) == (1, 0, 1)


class TestPRF1:
    def test_known_counts(self) -> None:
        precision, recall, f1 = prf1_from_counts(tp=1, fp=1, fn=0)
        assert precision == 0.5
        assert recall == 1.0
        assert round(f1, 4) == 0.6667


class TestRetrievalMetrics:
    def test_precision_at_k(self) -> None:
        assert precision_at_k(["x", "y", "z"], ["x", "z"], k=2) == 0.5

    def test_recall_at_k(self) -> None:
        assert recall_at_k(["x", "y", "z"], ["x", "z"], k=2) == 0.5

    def test_recall_empty_relevant_is_zero(self) -> None:
        assert recall_at_k(["x"], [], k=2) == 0.0


class TestRunner:
    def test_evaluate_example_produces_metrics(self) -> None:
        dataset = EvalDataset.model_validate(
            {
                "transcription": [{"reference": "a b c", "hypothesis": "a b c"}],
                "extraction": [
                    {
                        "gold_decisions": ["adoptar chromadb"],
                        "predicted_decisions": ["adoptar chromadb"],
                    }
                ],
                "retrieval": [{"retrieved": ["a", "b"], "relevant": ["a"]}],
            }
        )
        report = evaluate(dataset, k=2)
        names = {m.name for m in report.metrics}
        assert "transcription.wer_mean" in names
        assert "extraction.decisions.f1" in names
        assert "retrieval.precision_at_2" in names

        table = render_markdown(report)
        assert table.startswith("| Métrica | Valor |")

    def test_evaluate_with_run_metas_adds_performance(self) -> None:
        dataset = EvalDataset.model_validate(
            {"transcription": [{"reference": "a b", "hypothesis": "a b"}]}
        )
        run_metas = [
            {
                "total_cost_usd": 0.01,
                "total_llm_latency_s": 2.0,
                "total_input_tokens": 1000,
                "total_output_tokens": 500,
            },
            {
                "total_cost_usd": 0.03,
                "total_llm_latency_s": 4.0,
                "total_input_tokens": 3000,
                "total_output_tokens": 1500,
            },
        ]
        report = evaluate(dataset, k=2, run_metas=run_metas)
        values = {m.name: m.value for m in report.metrics}
        assert values["performance.runs"] == 2.0
        assert values["performance.total_cost_usd"] == 0.04
        assert values["performance.mean_cost_usd"] == 0.02
        assert values["performance.mean_llm_latency_s"] == 3.0
        assert values["performance.mean_input_tokens"] == 2000.0

    def test_evaluate_without_run_metas_has_no_performance(self) -> None:
        dataset = EvalDataset.model_validate(
            {"transcription": [{"reference": "a b", "hypothesis": "a b"}]}
        )
        report = evaluate(dataset, k=2)
        assert not any(m.name.startswith("performance.") for m in report.metrics)
