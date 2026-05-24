"""Abstracción para múltiples proveedores de LLM."""

from __future__ import annotations

import json
from typing import Protocol, TypeVar

from anthropic import Anthropic
from loguru import logger
from openai import OpenAI
from pydantic import BaseModel

from ..config import settings

T = TypeVar("T", bound=BaseModel)


class LLMProvider(Protocol):
    """Protocolo común para proveedores de LLM."""

    def complete(self, prompt: str, system: str | None = None) -> str:
        """Genera una respuesta de texto libre."""
        ...

    def complete_structured(
        self, prompt: str, schema: type[T], system: str | None = None
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

    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.anthropic_model
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        logger.info("Inicializado AnthropicProvider con modelo: {m}", m=self.model)

    def complete(self, prompt: str, system: str | None = None) -> str:
        """Genera respuesta de texto libre con Claude."""
        kwargs: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4000,
        }
        if system:
            kwargs["system"] = system

        response = self.client.messages.create(**kwargs)  # type: ignore[arg-type]
        block = response.content[0]
        if not hasattr(block, "text"):
            raise RuntimeError("Respuesta de Anthropic sin contenido de texto")
        return str(block.text)

    def complete_structured(
        self, prompt: str, schema: type[T], system: str | None = None
    ) -> T:
        """Genera respuesta JSON validada contra el schema."""
        json_instruction = (
            "Responde ÚNICAMENTE con un objeto JSON válido que cumpla este schema:\n"
            f"{json.dumps(schema.model_json_schema(), ensure_ascii=False)}\n\n"
            "No incluyas markdown, explicaciones ni texto adicional. Solo el JSON."
        )
        raw = self.complete(f"{prompt}\n\n{json_instruction}", system=system)
        parsed = json.loads(_strip_markdown_fences(raw))
        return schema.model_validate(parsed)


class OpenAIProvider:
    """Proveedor para OpenAI GPT."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.openai_model
        self.client = OpenAI(api_key=settings.openai_api_key)
        logger.info("Inicializado OpenAIProvider con modelo: {m}", m=self.model)

    def complete(self, prompt: str, system: str | None = None) -> str:
        """Genera respuesta de texto libre con GPT."""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=4000,
        )
        content = response.choices[0].message.content
        if content is None:
            raise RuntimeError("Respuesta de OpenAI sin contenido")
        return content

    def complete_structured(
        self, prompt: str, schema: type[T], system: str | None = None
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

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore[arg-type]
            response_format={"type": "json_object"},
            max_tokens=4000,
        )
        content = response.choices[0].message.content
        if content is None:
            raise RuntimeError("Respuesta de OpenAI sin contenido")
        parsed = json.loads(content)
        return schema.model_validate(parsed)


def get_provider() -> LLMProvider:
    """Factory que devuelve el proveedor configurado en settings."""
    name = settings.llm_provider
    if name == "anthropic":
        return AnthropicProvider()
    if name == "openai":
        return OpenAIProvider()
    if name == "ollama":
        # TODO: implementar en Fase 1 (cliente HTTP a OLLAMA_BASE_URL)
        raise ValueError("El proveedor 'ollama' aún no está implementado en Fase 0")
    raise ValueError(f"Proveedor desconocido: {name}")
