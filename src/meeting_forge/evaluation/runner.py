"""Orquestación de la evaluación (F1): dataset → métricas → reporte + tabla Markdown."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .metrics import (
    match_items,
    mean_wer,
    precision_at_k,
    prf1_from_counts,
    recall_at_k,
)
from .schemas import EvalDataset, EvalReport


def _add_performance(report: EvalReport, run_metas: Sequence[Mapping[str, object]]) -> None:
    """Agrega métricas de coste/latencia/tokens a partir de la telemetría (`run_meta`) de runs."""
    n = len(run_metas)
    if n == 0:
        return

    def _nums(key: str) -> list[float]:
        out: list[float] = []
        for rm in run_metas:
            val = rm.get(key, 0)
            out.append(float(val) if isinstance(val, (int, float)) else 0.0)
        return out

    costs = _nums("total_cost_usd")
    report.add("performance.runs", float(n))
    report.add("performance.total_cost_usd", sum(costs))
    report.add("performance.mean_cost_usd", sum(costs) / n)
    report.add("performance.mean_llm_latency_s", sum(_nums("total_llm_latency_s")) / n)
    report.add("performance.mean_input_tokens", sum(_nums("total_input_tokens")) / n)
    report.add("performance.mean_output_tokens", sum(_nums("total_output_tokens")) / n)


def evaluate(
    dataset: EvalDataset,
    k: int = 5,
    run_metas: Sequence[Mapping[str, object]] | None = None,
) -> EvalReport:
    """Calcula todas las métricas disponibles según las secciones presentes en el dataset.

    Si se pasan `run_metas` (lista de objetos `run_meta` de `result.json`), añade también métricas
    de rendimiento agregadas: coste total/medio, latencia media de LLM y tokens medios por run.
    """
    report = EvalReport()

    # --- Transcripción (WER) ---
    if dataset.transcription:
        pairs = [(e.reference, e.hypothesis) for e in dataset.transcription]
        report.add("transcription.wer_mean", mean_wer(pairs))

    # --- Extracción (precision/recall/F1) ---
    if dataset.extraction:
        d_tp = d_fp = d_fn = 0
        a_tp = a_fp = a_fn = 0
        for example in dataset.extraction:
            tp, fp, fn = match_items(example.gold_decisions, example.predicted_decisions)
            d_tp += tp
            d_fp += fp
            d_fn += fn
            tp, fp, fn = match_items(example.gold_actions, example.predicted_actions)
            a_tp += tp
            a_fp += fp
            a_fn += fn

        if d_tp + d_fp + d_fn:
            precision, recall, f1 = prf1_from_counts(d_tp, d_fp, d_fn)
            report.add("extraction.decisions.precision", precision)
            report.add("extraction.decisions.recall", recall)
            report.add("extraction.decisions.f1", f1)
        if a_tp + a_fp + a_fn:
            precision, recall, f1 = prf1_from_counts(a_tp, a_fp, a_fn)
            report.add("extraction.actions.precision", precision)
            report.add("extraction.actions.recall", recall)
            report.add("extraction.actions.f1", f1)

    # --- Retrieval (precision@k / recall@k) ---
    if dataset.retrieval:
        precisions = [precision_at_k(e.retrieved, e.relevant, k) for e in dataset.retrieval]
        recalls = [recall_at_k(e.retrieved, e.relevant, k) for e in dataset.retrieval]
        report.add(f"retrieval.precision_at_{k}", sum(precisions) / len(precisions))
        report.add(f"retrieval.recall_at_{k}", sum(recalls) / len(recalls))

    # --- Rendimiento (coste / latencia / tokens, desde la telemetría de runs reales) ---
    if run_metas:
        _add_performance(report, run_metas)

    return report


def render_markdown(report: EvalReport) -> str:
    """Renderiza el reporte como tabla Markdown lista para los anexos de la memoria."""
    lines = ["| Métrica | Valor |", "|---|---|"]
    for metric in report.metrics:
        lines.append(f"| `{metric.name}` | {metric.value:.4f} |")
    return "\n".join(lines)
