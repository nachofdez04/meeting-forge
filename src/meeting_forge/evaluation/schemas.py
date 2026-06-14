"""Esquemas del dataset de evaluación y del reporte de métricas (F1)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TranscriptionExample(BaseModel):
    """Par (referencia, hipótesis) para calcular WER."""

    reference: str
    hypothesis: str


class ExtractionExample(BaseModel):
    """Decisiones/tareas de referencia frente a las predichas, para precision/recall/F1."""

    gold_decisions: list[str] = Field(default_factory=list)
    predicted_decisions: list[str] = Field(default_factory=list)
    gold_actions: list[str] = Field(default_factory=list)
    predicted_actions: list[str] = Field(default_factory=list)


class RetrievalExample(BaseModel):
    """Resultados recuperados (ordenados) y conjunto relevante, para precision@k / recall@k."""

    retrieved: list[str] = Field(default_factory=list)
    relevant: list[str] = Field(default_factory=list)


class EvalDataset(BaseModel):
    """Dataset de evaluación: cualquier sección puede omitirse."""

    transcription: list[TranscriptionExample] = Field(default_factory=list)
    extraction: list[ExtractionExample] = Field(default_factory=list)
    retrieval: list[RetrievalExample] = Field(default_factory=list)


class MetricResult(BaseModel):
    """Una métrica con su valor."""

    name: str
    value: float


class EvalReport(BaseModel):
    """Conjunto de métricas calculadas."""

    metrics: list[MetricResult] = Field(default_factory=list)

    def add(self, name: str, value: float) -> None:
        self.metrics.append(MetricResult(name=name, value=round(value, 4)))
