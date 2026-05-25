# Arquitectura de MeetingForge

## Visión general

Sistema modular para transformar reuniones técnicas en documentación estructurada mediante IA generativa. Esta versión (Fase 0) cubre el pipeline básico audio → JSON.

## Pipeline principal (Fase 1)

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

## Fase 1: RAG con provenance

### Pipeline ampliado

```
                  Documentación
              (DOCS_PATH + repo/*.md)
                       │
                       ▼
          [scripts/index_docs.py]
            MarkdownChunker
            SentenceTransformerEmbeddings
            ChromaVectorStore (persistente)
                       │
                       ▼
              data/chromadb/
                       │
                       │ query()
                       ▼
       ┌────────────────────────────────┐
       │ rag.Retriever                  │
       │   sliding windows del transcript│
       │   top-K agregados + dedupe     │
       └────────────────────────────────┘
                       │
       Transcript ─────┘─► context block (#1, #2, ...)
                       ▼
              InsightsExtractor (prompt v2)
                       │
                       ▼
              MeetingInsights con sources
              (path + líneas + section)
```

### Componentes nuevos

- `rag/chunker.py` — chunking por jerarquía de headers (markdown-it-py); split por tamaño con overlap cuando una sección excede `chunk_max_chars`.
- `rag/embeddings.py` — `SentenceTransformerEmbeddings` (cache singleton del modelo).
- `rag/vector_store.py` — `ChromaVectorStore` con upsert idempotente (`chunk_id` como ID estable por hash).
- `rag/indexer.py` — `DocumentIndexer` recorre rutas, chunkea, embebe por batch (32), upsert.
- `rag/retriever.py` — `retrieve_for_transcript()` divide en ventanas, agrega, deduplica.

### Decisiones adicionales

- **Provenance vía marcadores `"#N"`**: el LLM elige índices (no copia paths); el extractor mapea a `SourceRef` después. Evita errores de copia y permite que sólo cambien los marcadores entre runs.
- **Schema raw interno**: `_RawMeetingInsights` con `sources: list[str]` para la conversación con el LLM; el schema público `MeetingInsights` ya contiene `SourceRef` objects.
- **Idempotencia**: `chunk_id = sha1(source_path:line_start-line_end:text)[:16]`. Reindexar el mismo archivo no duplica.
- **ChromaDB con cosine similarity**: `metadata={"hnsw:space": "cosine"}` y embeddings normalizados en `embed_texts`.
- **Fallback graceful**: si el store está vacío al correr `run_e2e.py`, log warning + ejecuta sin RAG (no rompe).

### Métricas de evaluación adicionales (Fase 1)

- **Retrieval quality**: precision@k contra un set anotado manualmente (¿están los chunks relevantes en el top-K?).
- **Cobertura de provenance**: % de decisiones que reciben al menos una cita cuando la docs sí cubre el tema.

## Fase 2: Generación de documentos con citas reales

### Pipeline ampliado

```
          MeetingInsights (con sources: list[SourceRef])
                     │
                     ▼
        [generation.DocumentGenerator]
          ┌──────────┬─────────────┐
          │          │             │
     ADR/decisión  ADR         Acta
      (LLM híbrido) consolidado  (template puro,
          │       (sintetizado)  0 llamadas LLM)
          ▼          │             │
   _RawADR con       │         render_acta()
   marcadores #N     │             │
          │          └──────┬──────┘
          ▼                 ▼
   rewrite_markers   footnotes [^N]
   #N → [^N]         deduplicados
          │
          ▼
   GeneratedDocument (.md)
   data/outputs/<meeting>/{adr,acta}/
```

### Componentes nuevos

- `generation/schemas.py` — `GeneratedDocument`, `MeetingMetadata`, `GenerationMode`, `DocumentKind`.
- `generation/citations.py` — `CitationRegistry` (dedupe por path+líneas), `rewrite_markers()` (#N→[^N]), `render_footnote_block()`, `escape_user_text()`.
- `generation/filenames.py` — `slug()` (NFKD, injection-safe), `build_adr_filename()`, `build_acta_filename()`.
- `generation/templates.py` — `render_adr_skeleton()` (string template), `render_acta()` (determinístico).
- `generation/adr_strategy.py` — `AdrStrategy`: llama al LLM con prompt `adr_v1.md`, post-procesa marcadores, ensambla ADR.
- `generation/acta_strategy.py` — `ActaStrategy`: renderiza acta sin LLM a partir de `MeetingInsights`.
- `generation/generator.py` — `DocumentGenerator`: orquesta los tres modos, graceful failure por modo.
- `prompts/generation/adr_v1.md` — prompt versionado para generar prosa de ADR con marcadores `#N`.

### Decisiones de diseño

- **Provenance reutilizada**: la Fase 2 no hace retrieval nuevo; consume los `SourceRef` ya resueltos en Fase 1.
- **Marcadores `#N` → `[^N]`**: el LLM emite `#N` (mismo vocabulario que Fase 1); `rewrite_markers()` los convierte a footnotes Markdown. Los markers dentro de code fences se preservan.
- **ADR consolidado sintetizado**: apila los ADRs por-decisión bajo un H1 común y deduplica el bloque de footnotes. Sin LLM extra.
- **Acta template-only**: cero llamadas LLM. Las citas se inyectan mecánicamente a partir de `decision.sources` y `action.sources`.
- **Contra inyección Markdown**: `escape_user_text()` escapa `[^` en texto generado por el LLM de Fase 1 para evitar colisiones de footnotes.
- **Contador ADR per-run**: `adr-0001-{slug}.md`, scoped a la reunión. Sin estado global compartido — idempotente.
- **ADR sin sources**: omite `## Referencias` (no placeholder).

### Parámetros de configuración (Fase 2)

| Variable | Default | Descripción |
|---|---|---|
| `GENERATION_ENABLED` | `true` | Activa/desactiva la generación |
| `GENERATION_MODES` | `adr-per-decision,acta` | Modos habilitados (CSV) |
| `ADR_PROMPT_VERSION` | `v1` | Versión del prompt de ADR |
| `GENERATION_MAX_TOKENS` | `4000` | Tope de tokens para generación |

### Estructura de outputs

```
data/outputs/<meeting_stem>/
├── <stem>_transcript.json
├── <stem>_result.json          ← ahora incluye generated_documents[]
├── adr/
│   ├── adr-0001-{slug}.md
│   └── adr-<stem>-consolidated.md
└── acta/
    └── acta-YYYY-MM-DD-<stem>.md
```

## Próximas fases

- **Fase 3 — UI**: Streamlit con transcript, insights y panel de evidencia (chunks recuperados).
- **Fase 4 — Integración Git**: commits/PRs automáticos con human-in-the-loop (`validation/`).
