"""Abstracción para múltiples proveedores de LLM."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any, Protocol, TypeVar

import anthropic
import openai
from anthropic import Anthropic
from loguru import logger
from openai import OpenAI
from pydantic import BaseModel

from ..config import settings
from ..observability import TelemetryCollector

T = TypeVar("T", bound=BaseModel)
_R = TypeVar("_R")


def _retryable_errors() -> tuple[type[Exception], ...]:
    """Tipos de error transitorios (rate limit, timeout, conexión, 5xx) de ambos SDKs."""
    names = ("RateLimitError", "APITimeoutError", "APIConnectionError", "InternalServerError")
    found: list[type[Exception]] = []
    for module in (anthropic, openai):
        for name in names:
            err = getattr(module, name, None)
            if isinstance(err, type) and issubclass(err, Exception):
                found.append(err)
    return tuple(found)


_RETRYABLE: tuple[type[Exception], ...] = _retryable_errors()


def _with_retries(
    call: Callable[[], _R],
    *,
    retries: int,
    base_delay: float,
    retryable: tuple[type[Exception], ...] = _RETRYABLE,
) -> _R:
    """Ejecuta `call` reintentando ante errores transitorios con backoff exponencial (F12)."""
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return call()
        except retryable as exc:
            last_exc = exc
            if attempt >= retries:
                break
            delay = base_delay * (2**attempt)
            logger.warning(
                "Error transitorio del LLM (intento {a}/{n}): {e}. Reintento en {d:.1f}s",
                a=attempt + 1,
                n=retries + 1,
                e=exc,
                d=delay,
            )
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc


def _usage_tokens(response: object, in_attr: str, out_attr: str) -> tuple[int, int]:
    """Extrae (input_tokens, output_tokens) de la respuesta de forma defensiva."""
    usage = getattr(response, "usage", None)
    return (
        int(getattr(usage, in_attr, 0) or 0),
        int(getattr(usage, out_attr, 0) or 0),
    )


class LLMProvider(Protocol):
    """Protocolo común para proveedores de LLM."""

    def complete(
        self, prompt: str, system: str | None = None, max_tokens: int | None = None
    ) -> str:
        """Genera una respuesta de texto libre."""
        ...

    def complete_structured(
        self,
        prompt: str,
        schema: type[T],
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> T:
        """Genera una respuesta validada contra un schema Pydantic."""
        ...


def _strip_markdown_fences(raw: str) -> str:
    """Limpia fences ```json ... ``` que algunos modelos añaden al JSON."""
    cleaned = raw.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[len("```json") :]
    elif cleaned.startswith("```"):
        cleaned = cleaned[len("```") :]
    if cleaned.endswith("```"):
        cleaned = cleaned[: -len("```")]
    return cleaned.strip()


class AnthropicProvider:
    """Proveedor para Anthropic Claude."""

    def __init__(
        self, model: str | None = None, collector: TelemetryCollector | None = None
    ) -> None:
        self.model = model or settings.anthropic_model
        if not settings.anthropic_api_key:
            raise ValueError(
                "Falta ANTHROPIC_API_KEY. Defínela en .env o cambia LLM_PROVIDER (openai/ollama)."
            )
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.collector = collector
        logger.info("Inicializado AnthropicProvider con modelo: {m}", m=self.model)

    def complete(
        self, prompt: str, system: str | None = None, max_tokens: int | None = None
    ) -> str:
        """Genera respuesta de texto libre con Claude."""
        kwargs: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens or settings.generation_max_tokens,
        }
        if system:
            kwargs["system"] = system

        def _create() -> Any:
            return self.client.messages.create(**kwargs)  # type: ignore[call-overload]

        start = time.perf_counter()
        response = _with_retries(
            _create,
            retries=settings.llm_max_retries,
            base_delay=settings.llm_retry_base_delay,
        )
        latency = time.perf_counter() - start
        if self.collector is not None:
            in_tok, out_tok = _usage_tokens(response, "input_tokens", "output_tokens")
            self.collector.record_llm_call(
                provider="anthropic",
                model=self.model,
                input_tokens=in_tok,
                output_tokens=out_tok,
                latency_s=latency,
            )

        block = response.content[0]
        if not hasattr(block, "text"):
            raise RuntimeError("Respuesta de Anthropic sin contenido de texto")
        return str(block.text)

    def complete_structured(
        self,
        prompt: str,
        schema: type[T],
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> T:
        """Genera respuesta JSON validada contra el schema."""
        json_instruction = (
            "Responde ÚNICAMENTE con un objeto JSON válido que cumpla este schema:\n"
            f"{json.dumps(schema.model_json_schema(), ensure_ascii=False)}\n\n"
            "No incluyas markdown, explicaciones ni texto adicional. Solo el JSON."
        )
        raw = self.complete(f"{prompt}\n\n{json_instruction}", system=system, max_tokens=max_tokens)
        parsed = json.loads(_strip_markdown_fences(raw))
        return schema.model_validate(parsed)


class OpenAIProvider:
    """Proveedor para OpenAI GPT."""

    _provider_name = "openai"

    def __init__(
        self, model: str | None = None, collector: TelemetryCollector | None = None
    ) -> None:
        self.model = model or settings.openai_model
        if not settings.openai_api_key:
            raise ValueError(
                "Falta OPENAI_API_KEY. Defínela en .env o cambia LLM_PROVIDER (anthropic/ollama)."
            )
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.collector = collector
        logger.info("Inicializado OpenAIProvider con modelo: {m}", m=self.model)

    def _record(self, response: object, latency: float) -> None:
        if self.collector is None:
            return
        in_tok, out_tok = _usage_tokens(response, "prompt_tokens", "completion_tokens")
        self.collector.record_llm_call(
            provider=self._provider_name,
            model=self.model,
            input_tokens=in_tok,
            output_tokens=out_tok,
            latency_s=latency,
        )

    def complete(
        self, prompt: str, system: str | None = None, max_tokens: int | None = None
    ) -> str:
        """Genera respuesta de texto libre con GPT."""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        def _create() -> Any:
            return self.client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=max_tokens or settings.generation_max_tokens,
            )

        start = time.perf_counter()
        response = _with_retries(
            _create,
            retries=settings.llm_max_retries,
            base_delay=settings.llm_retry_base_delay,
        )
        self._record(response, time.perf_counter() - start)
        content = response.choices[0].message.content
        if content is None:
            raise RuntimeError("Respuesta de OpenAI sin contenido")
        return str(content)

    def complete_structured(
        self,
        prompt: str,
        schema: type[T],
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> T:
        """Genera respuesta estructurada usando response_format JSON."""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})

        json_instruction = (
            "Responde con un JSON que cumpla este schema:\n"
            f"{json.dumps(schema.model_json_schema(), ensure_ascii=False)}"
        )
        messages.append({"role": "user", "content": f"{prompt}\n\n{json_instruction}"})

        def _create() -> Any:
            return self.client.chat.completions.create(  # type: ignore[call-overload]
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                max_tokens=max_tokens or settings.generation_max_tokens,
            )

        start = time.perf_counter()
        response = _with_retries(
            _create,
            retries=settings.llm_max_retries,
            base_delay=settings.llm_retry_base_delay,
        )
        self._record(response, time.perf_counter() - start)
        content = response.choices[0].message.content
        if content is None:
            raise RuntimeError("Respuesta de OpenAI sin contenido")
        parsed = json.loads(content)
        return schema.model_validate(parsed)


class OllamaProvider(OpenAIProvider):
    """Proveedor para Ollama local vía su API compatible con OpenAI (`/v1`).

    Reutiliza la lógica de OpenAIProvider apuntando el cliente a `OLLAMA_BASE_URL`. Inferencia local
    y gratuita; el coste estimado será 0 (el modelo no está en la tabla de precios). Cierra B6.
    """

    _provider_name = "ollama"

    def __init__(
        self, model: str | None = None, collector: TelemetryCollector | None = None
    ) -> None:
        self.model = model or settings.ollama_model
        base_url = f"{settings.ollama_base_url.rstrip('/')}/v1"
        # Ollama no exige API key real; su capa compatible-OpenAI acepta cualquier valor.
        self.client = OpenAI(base_url=base_url, api_key="ollama")
        self.collector = collector
        logger.info(
            "Inicializado OllamaProvider (modelo={m}, base_url={u})", m=self.model, u=base_url
        )


def get_provider(collector: TelemetryCollector | None = None) -> LLMProvider:
    """Factory que devuelve el proveedor configurado en settings.

    Si se pasa un `collector`, el proveedor registrará en él cada llamada (tokens, latencia, coste).
    """
    name = settings.llm_provider
    if name == "anthropic":
        return AnthropicProvider(collector=collector)
    if name == "openai":
        return OpenAIProvider(collector=collector)
    if name == "ollama":
        return OllamaProvider(collector=collector)
    raise ValueError(f"Proveedor desconocido: {name}")
