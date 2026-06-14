"""Tests del módulo de telemetría (F2)."""

from __future__ import annotations

from meeting_forge.observability import TelemetryCollector, estimate_cost_usd


class TestEstimateCost:
    def test_known_model(self) -> None:
        # gpt-4o-mini: (0.15, 0.6) USD por 1M tokens
        cost = estimate_cost_usd("gpt-4o-mini", 1_000_000, 1_000_000)
        assert round(cost, 4) == round(0.15 + 0.6, 4)

    def test_unknown_model_is_zero(self) -> None:
        assert estimate_cost_usd("modelo-inexistente", 1000, 1000) == 0.0


class TestTelemetryCollector:
    def test_records_calls_and_totals(self) -> None:
        c = TelemetryCollector()
        c.record_llm_call(
            provider="openai",
            model="gpt-4o-mini",
            input_tokens=1000,
            output_tokens=2000,
            latency_s=0.5,
        )
        c.record_llm_call(
            provider="openai",
            model="gpt-4o-mini",
            input_tokens=500,
            output_tokens=500,
            latency_s=0.25,
        )
        t = c.build()
        assert len(t.llm_calls) == 2
        assert t.total_input_tokens == 1500
        assert t.total_output_tokens == 2500
        assert t.total_llm_latency_s == 0.75
        assert t.total_cost_usd > 0
        assert t.cost_complete is True

    def test_unknown_model_marks_cost_incomplete(self) -> None:
        c = TelemetryCollector()
        c.record_llm_call(
            provider="x",
            model="desconocido",
            input_tokens=10,
            output_tokens=10,
            latency_s=0.1,
        )
        t = c.build()
        assert t.cost_complete is False
        assert t.total_cost_usd == 0.0

    def test_phase_records_timing(self) -> None:
        c = TelemetryCollector()
        with c.phase("demo"):
            pass
        t = c.build()
        assert [p.name for p in t.phases] == ["demo"]
        assert t.phases[0].duration_s >= 0.0

    def test_run_id_is_stable(self) -> None:
        c = TelemetryCollector()
        assert c.build().run_id == c.run_id
