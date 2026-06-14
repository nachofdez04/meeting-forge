"""Telemetría por ejecución (Fase A · F2): tiempos por fase, tokens, latencia y coste LLM.

Diseño minimalista y sin estado global: se crea un `TelemetryCollector` por run, se inyecta en
los proveedores LLM (que registran cada llamada) y se envuelven las fases con `collector.phase(...)`.
Al final, `collector.build()` produce un `RunTelemetry` serializable que se persiste en `result.json`.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from pydantic import BaseModel, Field

# Precios aproximados en USD por 1M de tokens (entrada, salida). Ajusta a las tarifas vigentes.
# Modelos no listados → coste 0.0 (se marca is_estimated=False a nivel de run si hubo desconocidos).
_PRICES_USD_PER_1M: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-20250514": (3.0, 15.0),
    "claude-opus-4-20250514": (15.0, 75.0),
    "claude-3-5-haiku-20241022": (0.8, 4.0),
    "gpt-4o-2024-08-06": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estima el coste de una llamada. Devuelve 0.0 si el modelo no está en la tabla de precios."""
    price = _PRICES_USD_PER_1M.get(model)
    if price is None:
        return 0.0
    price_in, price_out = price
    return (input_tokens / 1_000_000) * price_in + (output_tokens / 1_000_000) * price_out


class LLMCallRecord(BaseModel):
    """Registro de una única llamada al LLM."""

    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0
    cost_usd: float = 0.0
    cost_known: bool = True


class PhaseTiming(BaseModel):
    """Duración de una fase del pipeline."""

    name: str
    duration_s: float


class RunTelemetry(BaseModel):
    """Telemetría agregada de una ejecución completa del pipeline."""

    run_id: str
    started_at: datetime
    phases: list[PhaseTiming] = Field(default_factory=list)
    llm_calls: list[LLMCallRecord] = Field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    total_llm_latency_s: float = 0.0
    cost_complete: bool = True
    config: dict[str, object] = Field(default_factory=dict)


class TelemetryCollector:
    """Acumula tiempos por fase y registros de llamadas LLM durante un run."""

    def __init__(self, config: dict[str, object] | None = None) -> None:
        self.run_id = uuid.uuid4().hex[:12]
        self.started_at = datetime.now(tz=UTC)
        self._phases: list[PhaseTiming] = []
        self._calls: list[LLMCallRecord] = []
        self._config: dict[str, object] = config or {}

    def record_llm_call(
        self,
        *,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_s: float,
    ) -> None:
        """Registra una llamada al LLM con su uso de tokens, latencia y coste estimado."""
        cost_known = model in _PRICES_USD_PER_1M
        self._calls.append(
            LLMCallRecord(
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_s=round(latency_s, 3),
                cost_usd=round(estimate_cost_usd(model, input_tokens, output_tokens), 6),
                cost_known=cost_known,
            )
        )

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        """Mide la duración de un bloque y la registra como fase con el nombre dado."""
        start = time.perf_counter()
        try:
            yield
        finally:
            self._phases.append(
                PhaseTiming(name=name, duration_s=round(time.perf_counter() - start, 3))
            )

    def build(self) -> RunTelemetry:
        """Construye el `RunTelemetry` agregado para persistir."""
        return RunTelemetry(
            run_id=self.run_id,
            started_at=self.started_at,
            phases=list(self._phases),
            llm_calls=list(self._calls),
            total_input_tokens=sum(c.input_tokens for c in self._calls),
            total_output_tokens=sum(c.output_tokens for c in self._calls),
            total_cost_usd=round(sum(c.cost_usd for c in self._calls), 6),
            total_llm_latency_s=round(sum(c.latency_s for c in self._calls), 3),
            cost_complete=all(c.cost_known for c in self._calls),
            config=dict(self._config),
        )
