"""Métricas de evaluación puras y testeables (F1).

Cubre la propuesta del TFM (objetivo 7):
- **Transcripción**: WER (Word Error Rate) por distancia de edición a nivel de palabra.
- **Extracción**: precision/recall/F1 emparejando ítems por solape de tokens (Jaccard).
- **Retrieval**: precision@k y recall@k.

Sin dependencias externas: todo se calcula con la librería estándar para que la evaluación sea
reproducible y rápida (apta para CI y para los anexos de la memoria).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence


def _tokenize(text: str) -> list[str]:
    return text.split()


def word_error_rate(reference: str, hypothesis: str) -> float:
    """WER = (sustituciones + inserciones + borrados) / palabras de referencia.

    0.0 = transcripción perfecta. Si la referencia está vacía, devuelve 0.0 (o 1.0 si hay hipótesis).
    """
    ref = _tokenize(reference)
    hyp = _tokenize(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0

    # Distancia de edición (Levenshtein) a nivel de palabra con DP por filas.
    prev = list(range(len(hyp) + 1))
    for i, ref_word in enumerate(ref, start=1):
        cur = [i] + [0] * len(hyp)
        for j, hyp_word in enumerate(hyp, start=1):
            cost = 0 if ref_word == hyp_word else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[len(hyp)] / len(ref)


def mean_wer(pairs: Sequence[tuple[str, str]]) -> float:
    """WER medio sobre una lista de pares (referencia, hipótesis)."""
    if not pairs:
        return 0.0
    return sum(word_error_rate(ref, hyp) for ref, hyp in pairs) / len(pairs)


def _normalize(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    lowered = ascii_text.lower()
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


def _token_set(text: str) -> set[str]:
    return set(_normalize(text).split())


def _jaccard(a: str, b: str) -> float:
    ta, tb = _token_set(a), _token_set(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def prf1_from_counts(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    """Devuelve (precision, recall, f1) a partir de los conteos."""
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return precision, recall, f1


def match_items(
    gold: Sequence[str], predicted: Sequence[str], threshold: float = 0.5
) -> tuple[int, int, int]:
    """Empareja predicciones con gold por solape Jaccard ≥ threshold (greedy 1:1).

    Devuelve (true_positives, false_positives, false_negatives).
    """
    used_gold: set[int] = set()
    tp = 0
    for pred in predicted:
        best_idx = -1
        best_score = 0.0
        for gi, gold_item in enumerate(gold):
            if gi in used_gold:
                continue
            score = _jaccard(pred, gold_item)
            if score > best_score:
                best_score = score
                best_idx = gi
        if best_idx >= 0 and best_score >= threshold:
            used_gold.add(best_idx)
            tp += 1
    fp = len(predicted) - tp
    fn = len(gold) - tp
    return tp, fp, fn


def precision_at_k(retrieved: Sequence[str], relevant: Sequence[str], k: int) -> float:
    """Fracción de los top-k recuperados que son relevantes."""
    if k <= 0:
        return 0.0
    topk = list(retrieved)[:k]
    if not topk:
        return 0.0
    rel = set(relevant)
    return sum(1 for item in topk if item in rel) / len(topk)


def recall_at_k(retrieved: Sequence[str], relevant: Sequence[str], k: int) -> float:
    """Fracción de los relevantes que aparecen en los top-k recuperados."""
    rel = set(relevant)
    if not rel:
        return 0.0
    topk = set(list(retrieved)[:k])
    return len(topk & rel) / len(rel)
