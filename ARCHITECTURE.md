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
| LLM | Anthropic Claude, OpenAI GPT, Ollama (API compatible con OpenAI) |
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

## Fase 3: UI — Visor Streamlit

### Pipeline ampliado

```text
      data/outputs/<meeting_id>/
        ├── *_result.json      ← transcript + insights + SourceRefs
        └── {adr,acta}/*.md   ← documentos generados
                  │
                  ▼
    [ui/loader.py]
      list_meetings()          ← escanea data/outputs/, ordena por mtime
      load_meeting()           ← deserializa result.json → MeetingData
      load_generated_docs()    ← lee los .md de adr/ y acta/
                  │
                  ▼
    [ui/evidence.py]
      read_source_slice()      ← para cada SourceRef, lee las líneas
                               indicadas del archivo fuente original
                  │
                  ▼
    [ui/app.py]  Streamlit
      Sidebar: meeting picker + metadata del run
      Tabs:
        Resumen    → summary + topics + métricas
        Transcript → tabla de segmentos con timestamps
        Insights   → decisiones/tareas con fuentes expandibles
        Evidencia  → rodajas de archivos fuente por decisión
        Documentos → render + descarga de ADRs y Actas
```

### Componentes nuevos

- `ui/loader.py` — `list_meetings()`, `load_meeting()`, `load_generated_docs()`. Sin dependencia de Streamlit (testeables de forma aislada).
- `ui/evidence.py` — `read_source_slice()`: resuelve `SourceRef.source_path` relativo al project root, lee el slice de líneas con `lru_cache` por archivo.
- `ui/app.py` — app Streamlit. `@st.cache_data` en las funciones de carga para evitar releer JSON en cada interacción.

### Decisiones de diseño

- **Visor read-only**: el pipeline sigue ejecutándose vía `scripts/run_e2e.py`. La UI no replica ni orquesta el pipeline.
- **Evidencia desde archivos fuente**: los chunks recuperados por el retriever no se persisten en disco; la UI lee las rodajas directamente de los archivos de documentación originales a partir de los `SourceRef` (path + líneas). Requiere que la documentación siga accesible en el mismo path relativo.
- **Graceful fallback**: si el archivo fuente de un `SourceRef` no existe (movido o eliminado), la UI muestra un `st.warning` con el motivo sin romper la navegación.
- **Streamlit como dep opcional**: declarado en `[dependency-groups] ui` de `pyproject.toml`, no en deps principales. Se instala con `uv sync --group ui`.

### Parámetros de configuración (Fase 3)

No se añaden nuevas variables de entorno. La UI reutiliza `settings.data_dir` (para localizar `data/outputs/`) y `settings.project_root` (como base para resolver `SourceRef.source_path`).

## Fase 4: Integración Git con Human-in-the-Loop

### Pipeline ampliado

```text
      data/outputs/<meeting_id>/
        ├── adr/*.md, acta/*.md   ← generados por Fase 2 (read-only)
        └── validation.json       ← NUEVO: estado HITL por documento

      Tab "Validación" (Streamlit UI)
        ├── Por cada doc: Preview / Editar + Aprobar / Rechazar / Reset
        └── Botón "Publicar a Git" (habilitado si ≥1 aprobado)
                  │
                  ▼
        git_integration.publisher.publish_meeting()
                  │
                  ├── 1. ensure_repo (clone/validate)
                  ├── 2. checkout base branch + pull
                  ├── 3. crear rama meeting-forge/<meeting_id>-<date>
                  ├── 4. escribir docs aprobados en docs_subdir/
                  ├── 5. git add + commit + push
                  └── 6. gh pr create → PR URL
                  │
                  ▼
        publish.json escrito + UI muestra PR URL
```

### Componentes nuevos

- `validation/schemas.py` — `ValidationStatus` enum, `ValidationRecord`, `MeetingValidationState`.
- `validation/store.py` — `load_state()`, `save_state()` (atómico), `initialize_pending()` (idempotente), `mark_approved()`, `mark_rejected()`, `reset_record()`, `get_effective_content()`.
- `git_integration/schemas.py` — `PublishRequest`, `PublishResult`.
- `git_integration/templates.py` — `build_branch_name()`, `build_commit_message()`, `build_pr_title()`, `build_pr_body()`.
- `git_integration/repo.py` — wrappers sobre `git` CLI: `ensure_repo()`, `checkout_branch()`, `pull()`, `write_files()`, `add_and_commit()`, `push()`.
- `git_integration/pr.py` — `is_gh_available()`, `create_pr()` (vía `gh` CLI).
- `git_integration/publisher.py` — `publish_meeting()` (orquestador), `load_publish_result()`.

### Decisiones de diseño

- **Estado persistido en `validation.json`**: permite que la UI muestre el progreso entre reruns y que el publicador sepa qué docs publicar. Escritura atómica (tmp + rename).
- **Contenido editado sobreescribe el original**: si el usuario edita un documento en la UI, `get_effective_content()` devuelve la versión editada al publicador. El archivo original en `data/outputs/` no se modifica.
- **Un commit + un PR por reunión**: todos los docs aprobados van en un solo commit en una rama `meeting-forge/<meeting_id>-<date>`. La granularidad de revisión la da el diff del PR.
- **`gh` CLI para PRs**: sin dependencias Python adicionales. El usuario gestiona la autenticación con `gh auth login`. Si `gh` no está disponible, el commit y push se completan igualmente y el publisher logea un warning.
- **Repo destino externo**: los docs auto-generados van a un repo configurado vía `GIT_TARGET_REPO_PATH`, separado del repo de código.
- **Desactivado por defecto**: `GIT_INTEGRATION_ENABLED=false`. El tab Validación siempre es visible, pero el botón "Publicar a Git" se deshabilita con mensaje explicativo.

### Parámetros de configuración (Fase 4)

| Variable | Default | Descripción |
|---|---|---|
| `GIT_INTEGRATION_ENABLED` | `false` | Activa/desactiva la publicación |
| `GIT_TARGET_REPO_PATH` | `None` | Ruta local del repo destino |
| `GIT_TARGET_REMOTE` | `None` | URL git para clone inicial (opcional) |
| `GIT_DOCS_SUBDIR` | `docs/meetings` | Subdir dentro del repo destino |
| `GIT_BASE_BRANCH` | `main` | Rama base del repo destino |
| `GIT_BRANCH_PREFIX` | `meeting-forge/` | Prefijo de ramas creadas |
| `GH_EXECUTABLE` | `gh` | Path al ejecutable gh CLI |

### Estructura de outputs (Fase 4)

```
data/outputs/<meeting_stem>/
├── <stem>_transcript.json
├── <stem>_result.json
├── adr/*.md
├── acta/*.md
├── validation.json       ← estado HITL (pending/approved/rejected/edited)
└── publish.json          ← resultado de publicación (branch, commit SHA, PR URL)
```
