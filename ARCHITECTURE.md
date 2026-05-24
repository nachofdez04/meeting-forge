# Arquitectura de MeetingForge

## Visión general

Sistema modular para transformar reuniones técnicas en documentación estructurada mediante IA generativa. Esta versión (Fase 0) cubre el pipeline básico audio → JSON.

## Pipeline principal (Fase 0)

```
        Audio de reunión (.wav, .mp3, …)
                  │
                  ▼
   ┌─────────────────────────────────┐
   │ [Módulo 1] meeting_forge.ingestion │
   │   WhisperTranscriber (faster-whisper) │
   │   → Transcript (segmentos timestamped)│
   └─────────────────────────────────┘
                  │
                  ▼
   ┌─────────────────────────────────┐
   │ [Módulo 2] meeting_forge.analysis │
   │   InsightsExtractor               │
   │   provider-agnostic (Anthropic |  │
   │   OpenAI | Ollama)                │
   │   → MeetingInsights (decisiones,  │
   │     tareas, temas, resumen)       │
   └─────────────────────────────────┘
                  │
                  ▼
            JSON estructurado
            (data/outputs/*.json)
```

## Decisiones de arquitectura clave

### 1. Abstracción multi-proveedor de LLM

**Decisión**: interfaz `LLMProvider` (Protocol) con múltiples backends (Anthropic, OpenAI, Ollama).

**Justificación**:
- Permite comparar proveedores en la fase de evaluación (relevante para TFM).
- Evita vendor lock-in.
- Facilita migración según coste/calidad.

**Implementación**: patrón Factory (`get_provider()`) + `Protocol` typing en [`analysis/llm_client.py`](src/meeting_forge/analysis/llm_client.py).

**Nota sobre sync vs async**: el spec inicial declaraba el Protocol como `async`, pero las implementaciones de Anthropic/OpenAI usadas son síncronas. Mantenemos métodos `sync` hasta que aparezca un caso de uso real (p.ej. procesar varias reuniones en paralelo) que justifique la conversión.

### 2. Transcripción local vs cloud

**Decisión**: `faster-whisper` local, con VAD (Voice Activity Detection) integrado.

**Justificación**:
- Sin coste recurrente de API por minuto de audio.
- Privacidad: el audio nunca sale de la máquina.
- Control total sobre modelo y calidad.
- Compromiso: requiere GPU para velocidad óptima; en CPU usar `medium` + `int8`.

### 3. Structured Outputs con Pydantic

**Decisión**: todos los outputs del LLM se validan contra schemas Pydantic v2.

**Justificación**:
- Type safety end-to-end.
- Validación automática de formatos.
- Serialización JSON gratis (`model_dump_json()`).
- Base para generación de documentación posterior.

**Estrategia por proveedor**:
- **OpenAI**: usa `response_format={"type": "json_object"}` nativo.
- **Anthropic**: inyecta `model_json_schema()` en el prompt + parseo con limpieza de fences markdown.

### 4. Prompts versionados en archivos

**Decisión**: los prompts viven como Markdown en `prompts/` y se cargan en runtime.

**Justificación**:
- Versionado en Git, diffeable, blameable.
- A/B testing trivial: cambiar `v1.md` → `v2.md`.
- Separación de lógica y texto.
- Colaboración con perfiles no-técnicos posible.

## Stack técnico

| Capa | Herramienta |
|---|---|
| Lenguaje | Python 3.11+ |
| Gestión deps | uv |
| Transcripción ASR | faster-whisper |
| LLM | Anthropic Claude, OpenAI GPT (Ollama planificado) |
| Validación | Pydantic v2 |
| Settings | pydantic-settings |
| CLI | typer |
| Logging | loguru |
| Linting | ruff |
| Type checking | mypy --strict |
| Testing | pytest |

## Configuración

Toda la configuración pasa por variables de entorno cargadas vía `pydantic-settings` desde `.env`. Ver [`.env.example`](.env.example).

- `Settings` usa `model_post_init` para crear los directorios `data/{raw,transcripts,outputs}` al instanciarse.
- El singleton `settings` se importa desde `meeting_forge.config`.

## Métricas de evaluación planificadas

1. **Transcripción**: WER (Word Error Rate) contra ground truth manual.
2. **Extracción**: Precision/Recall en detección de decisiones (vs ground truth).
3. **Performance**: Latencia E2E por minuto de audio, coste por reunión.
4. **Calidad**: Evaluación humana sobre ADRs generados (Fase 2+).

## Próximas fases

- **Fase 1 — RAG**: ChromaDB + sentence-transformers para indexar documentación Markdown existente y enriquecer la extracción con contexto del proyecto.
- **Fase 2 — Generación**: ADRs, actas y updates de docs a partir de los insights.
- **Fase 3 — UI**: Streamlit para subir audio y revisar outputs.
- **Fase 4 — Integración Git**: commits/PRs automáticos con human-in-the-loop.
