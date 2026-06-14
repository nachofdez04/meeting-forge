# Plan 02 · Features para mejorar el proyecto

> Parte de [`planes/`](00-orquestador.md). Funcionalidades **nuevas** que acercan el proyecto a la
> visión completa de `propuesta_tfm.pdf` y lo hacen más sólido y demostrable. Los bugs/deuda van en
> [`01-bugs-y-deuda-tecnica.md`](01-bugs-y-deuda-tecnica.md).

## Cómo leer este documento

- **Prioridad**: orientada a **completitud del TFM primero** (lo que cierra la memoria y la defensa).
- **Esfuerzo**: 🟢 < 1 día · 🟡 2–4 días · 🔴 1–2 semanas.
- Cada feature cita el **objetivo de la propuesta** que satisface y los **módulos** afectados.

## Estado de implementación

> Actualizado: **2026-05-31**. Árbol de trabajo (sin commitear). Gates: `ruff`/`mypy` ✅ · `pytest` **262 passed, 2 skipped**.

**✅ Completadas (Fase A · bloque académico)**

- **F2 — Observabilidad por run**: nuevo [`observability.py`](../src/meeting_forge/observability.py)
  (`TelemetryCollector`, `run_id`, tiempos por fase, tokens, latencia, coste estimado). Cableado en el cliente LLM
  y en [run_e2e.py](../scripts/run_e2e.py); se persiste como `run_meta` en `result.json`.
  Test: [test_observability.py](../tests/unit/test_observability.py).
- **F3 — Persistir metadata + evidencia**: `meeting_metadata` y `retrieved_evidence` (texto + score) en
  `result.json`; la UI relee la metadata al publicar. Cierra **TD7** y **TD8**.
- **F1 — Harness de evaluación**: paquete [`evaluation/`](../src/meeting_forge/evaluation) (WER, P/R/F1,
  precision@k/recall@k) + CLI [`scripts/evaluate.py`](../scripts/evaluate.py) + dataset de ejemplo
  [`evaluation/datasets/example.json`](../evaluation/datasets/example.json). Verificado end-to-end (genera tabla
  Markdown + `report.json`). Test: [test_evaluation_metrics.py](../tests/unit/test_evaluation_metrics.py).

**✅ Completadas (Fase C · producto)**

- **F9 — Robustez de ingesta de audio** (núcleo, sin deps nuevas): preprocesado opcional con **ffmpeg**
  (mono + 16 kHz + `loudnorm`) en [`preprocessor.py`](../src/meeting_forge/ingestion/preprocessor.py), tolerante a
  fallos (passthrough si está desactivado / sin ffmpeg / error), cableado en el transcriptor; idioma ya configurable
  (B4). Tests en [test_preprocessor.py](../tests/unit/test_preprocessor.py). Pendiente opcional: diarización real
  (pyannote) y fixture de audio con voz.
- **F8 — Modo automático opcional**: desactivado por defecto. Con `AUTO_APPROVE_ENABLED=true`, el pipeline
  **auto-aprueba solo los tipos en la allowlist** (`AUTO_APPROVE_KINDS`, default `acta`) marcándolos
  `auto_approved` (auditoría + badge en la UI); auto-publicación opcional (`AUTO_PUBLISH_ENABLED` +
  `GIT_INTEGRATION_ENABLED`) con **PRs borrador** (`GIT_PR_DRAFT`). Lógica aislada en
  [`automation.py`](../src/meeting_forge/automation.py). Tests en [test_automation.py](../tests/unit/test_automation.py).
- **F12 — Robustez de proveedores LLM** (núcleo): **validación de API keys al iniciar** con error accionable
  (Anthropic/OpenAI) y **retries con backoff exponencial** ante errores transitorios (rate limit, timeout, 5xx),
  configurables (`LLM_MAX_RETRIES`/`LLM_RETRY_BASE_DELAY`) ([llm_client.py](../src/meeting_forge/analysis/llm_client.py)).
  Ollama ya estaba (B6). Tests en [test_llm_client.py](../tests/unit/test_llm_client.py). Pendiente opcional:
  structured outputs estrictos (OpenAI `json_schema`).
- **F11 — UX de validación**: **"Aprobar" ya no descarta la edición en curso** (preserva el texto del editor,
  antes se perdía); se muestra el **diff de la edición vs el documento original generado**; botón aclarado a
  "Guardar edición y aprobar" ([app.py](../src/meeting_forge/ui/app.py)).
- **F10 — Empaquetado y demo** (núcleo): entrypoint CLI unificado `meeting-forge` (`run`/`index`/`eval`/
  `demo`/`check`) en [`cli.py`](../src/meeting_forge/cli.py) + [`pyproject.toml`](../pyproject.toml); **demo offline
  reproducible** sin API keys ni audio ([`demo.py`](../src/meeting_forge/demo.py) → acta determinística cargable por la
  UI); comando `check` de prerequisitos. Test en [test_demo.py](../tests/unit/test_demo.py). Pendiente opcional:
  Dockerfile.
- **F4 — Ejecutar el pipeline desde la UI** (objetivo 6): orquestación extraída a un servicio reutilizable
  [`pipeline.py`](../src/meeting_forge/pipeline.py) (`run_pipeline` con callback de progreso por fase); `run_e2e.py`
  es ahora un CLI fino sobre él; la UI tiene panel **➕ Procesar nueva reunión** (subir audio → ejecutar con
  `st.status` por fase → preselección del run nuevo) ([app.py](../src/meeting_forge/ui/app.py)). Tests de helpers en
  [test_pipeline.py](../tests/unit/test_pipeline.py).
- **F5 — Roadmap + documentación técnica** (objetivo 4): modos `roadmap-update`/`technical-doc-update`,
  [`UpdateStrategy`](../src/meeting_forge/generation/update_strategy.py) con **diff** vs documento existente
  ([diffing.py](../src/meeting_forge/generation/diffing.py)), prompts versionados, **autodescubrimiento** del doc a
  actualizar (`ROADMAP_PATH`/`TECH_DOC_PATH`), persistencia del `.diff` (sibling) y **render del diff en la UI**
  (visor + validación). Soporta tanto crear como **actualizar** documentos existentes.

**🟡 Parcial / siguiente sobre lo hecho**

- **F6** (endurecer RAG): hechos **B1**, **B2**, **B7**, **B8** y el **sync de borrados** (`sync_paths` + flag
  `--sync` en `index_docs.py`); pendiente: filtros por tipo/carpeta/fecha en el retrieval.
- **F7** (endurecer Git): hechos **TD9**, **B10**, **B11**, **B9**, **detección de repo sucio** (`ensure_clean`)
  y **fallback con URL de compare** (`build_compare_url`, mostrado en la UI); pendiente: modo `--dry-run`.
- **F1 (datos reales)**: el harness evalúa datasets estáticos; falta conectar predicciones del pipeline real y
  añadir latencia/coste (desde `run_meta`) a la tabla del reporte.

**⬜ Pendientes**: ninguna feature completa pendiente. Solo **flecos opcionales**: Dockerfile (F10),
structured outputs estrictos (F12), filtros de retrieval (F6), `--dry-run` de publicación (F7), diarización real (F9).

## Mapa propuesta → estado actual

La propuesta define 7 objetivos específicos. Estado observado:

| # | Objetivo de la propuesta | Estado | Feature relacionada |
|---|---|---|---|
| 1 | Pipeline de transcripción (audio → texto estructurado) | ✅ / 🟡 robustez | F9 |
| 2 | Análisis con LLM (decisiones, acuerdos, roadmap) | ✅ | — |
| 3 | RAG sobre Markdown en Git | ✅ / 🟡 fiabilidad | F6 |
| 4 | Generar actas **+ doc técnica + roadmap + ADRs** | 🟡 (solo actas+ADR) | **F5** |
| 5 | Human-in-the-loop (+ modo automático opcional) | ✅ / ❌ modo auto | F8 |
| 6 | UI: cargar audio, ver transcripciones, aprobar | ✅ | F4 hecho |
| 7 | **Evaluación por métricas** (WER, precisión, latencia, coste) | ❌ vacío | **F1** |

Las dos mayores brechas para el TFM son **F1 (evaluación)** y **F5 (doc técnica + roadmap)**, seguidas de
**F4 (ejecutar desde la UI)**.

---

## Resumen (tabla)

| ID | Feature | Prioridad | Esfuerzo | Cierra objetivo |
|---|---|---|---|---|
| F1 | Harness de evaluación + métricas | **P0** | 🔴 | #7 |
| F2 | Observabilidad y reproducibilidad por run | **P0** | 🟡 | base de #7 |
| F3 | Persistir metadata + evidencia en `result.json` | **P0/P1** | 🟡 | habilita #7 |
| F4 | Ejecutar el pipeline desde la UI | P1 | 🔴 | #6 |
| F5 | Doc técnica + roadmap (y actualizar docs existentes) | P1 | 🔴 | #4 |
| F6 | Endurecer RAG | P1 | 🟡 | #3 |
| F7 | Endurecer integración Git | P1 | 🟡 | #5 |
| F8 | Modo completamente automático opcional | P2 | 🟡 | #5 |
| F9 | Robustez de ingesta de audio | P2 | 🔴 | #1 |
| F10 | Empaquetado y demo | P2 | 🟡 | demostrabilidad |
| F11 | Pulido de UX de validación | P2 | 🟢 | #5/#6 |
| F12 | Robustez de proveedores LLM (Ollama, retries) | P3 | 🟡 | transversal |

---

## F1 · Harness de evaluación + métricas — **P0** 🔴 · objetivo #7

**Motivación.** Es **la mayor brecha** respecto a la propuesta (objetivo 7 explícito: *"Evaluar el sistema
mediante métricas relacionadas con calidad de transcripción, precisión en la detección de decisiones, calidad de
la documentación generada, latencia y coste de inferencia"*). Hoy [`evaluation/`](../evaluation) está **vacío**
(solo `.gitkeep`). Sin esto, la memoria no tiene capítulo cuantitativo.

**Alcance.**
- **Datasets anotados** (en `evaluation/datasets/`):
  - Transcripciones de referencia (ground truth) para **WER**.
  - Decisiones/tareas anotadas para **precision/recall/F1** de extracción.
  - Conjunto de queries/reuniones con chunks relevantes etiquetados para **precision@k / recall@k** del RAG.
  - Un **fixture sintético** de reunión pequeño (texto + audio corto opcional) para correr sin depender de datos reales.
- **Métricas** (en `evaluation/metrics/` + `scripts/evaluate.py`):
  - WER (p.ej. `jiwer` o implementación propia).
  - P/R/F1 de decisiones y tareas (matching por similitud + revisión).
  - precision@k / recall@k del retriever.
  - Latencia por fase y **coste estimado** por reunión y por proveedor (consume la telemetría de **F2**).
  - Rúbrica humana (plantilla Markdown) para calidad de ADR/acta.
- **Salida reproducible**: JSON + tablas Markdown/CSV listas para anexos de la memoria.

**Módulos.** Nuevo paquete `evaluation/` (scripts + datasets), `scripts/evaluate.py`, y ganchos de telemetría en
`analysis/llm_client.py` y `rag/retriever.py`.

**Criterio de aceptación.** `uv run python scripts/evaluate.py` produce, sobre el dataset de ejemplo, una tabla con
WER, P/R/F1, precision@k, latencia y coste — de forma determinista y reproducible.

**Dependencias.** Requiere **F2** (telemetría de coste/latencia), **F3** (evidencia persistida) y, para que el RAG
evaluado sea representativo, los arreglos **B1/B2** (índice limpio).

---

## F2 · Observabilidad y reproducibilidad por run — **P0** 🟡 · base de #7

**Motivación.** Sin medir no hay evaluación, y sin reproducibilidad la memoria no es defendible.

**Alcance.** Por cada ejecución capturar y persistir:
- `run_id` único (UUID) y timestamp.
- Tiempos por fase (transcripción, retrieval, extracción, generación).
- Por cada llamada LLM: proveedor, modelo, tokens in/out, latencia, **coste estimado** (tabla de precios por modelo).
- Versión de prompt usada, hash de la documentación indexada, snapshot de la config efectiva.
- Logs estructurados por fase (loguru con campos consistentes).

**Módulos.** Nuevo `meeting_forge/observability/` (o `telemetry.py`) ligero; instrumentar
`analysis/llm_client.py`, `scripts/run_e2e.py`, `rag/retriever.py`. Persistir en `result.json` (sección `run_meta`).

**Criterio de aceptación.** `result.json` incluye `run_meta` con tiempos, tokens, coste y versiones; los logs
muestran cada fase con su duración.

---

## F3 · Persistir metadata de reunión + evidencia recuperada — **P0/P1** 🟡 · habilita #7

**Motivación.** Formaliza **TD7 + TD8**. Hoy se pierde fecha/título en la UI y la evidencia depende de ficheros
vivos. Para reproducibilidad y para que UI/publisher sean fieles, hay que persistir estos datos.

**Alcance.**
- Guardar el `MeetingMetadata` usado (fecha, título, `source_audio`) en `result.json`; la UI/publisher lo releen
  en vez de reconstruir con `date=None`.
- Guardar, junto a cada `SourceRef`, el **texto exacto** del chunk recuperado y su `score` (y ventana/idx).

**Módulos.** `scripts/run_e2e.py` (escritura), `ui/app.py` + `ui/loader.py` (lectura), `analysis/extractor.py`
(emitir el chunk text usado), esquemas en `rag/schemas.py`.

**Criterio de aceptación.** Tras un run, borrar/mover un doc fuente **no** rompe el panel de evidencia; el PR/rama
llevan la fecha correcta.

---

## F4 · Ejecutar el pipeline desde la UI — P1 🔴 · objetivo #6

**Motivación.** La propuesta describe una UI que *"permita cargar audio, visualizar transcripciones y aprobar
actualizaciones"*. La UI actual ([`ui/app.py`](../src/meeting_forge/ui/app.py)) es un **visor read-only** de runs ya
procesados; falta el "cargar audio" y "ejecutar".

**Alcance.**
- Subida de audio desde Streamlit (`st.file_uploader`).
- Lanzar el pipeline (transcripción → RAG → extracción → generación) con **progreso por fases** y manejo de errores.
- Mostrar el run recién creado sin relanzar la app a mano.

**Diseño (clave).** Extraer la lógica de orquestación de [`scripts/run_e2e.py`](../scripts/run_e2e.py) a una **capa
de servicio** reutilizable (p.ej. `meeting_forge/pipeline.py`) que llamen tanto el CLI como la UI. Evita duplicar el
pipeline. Encaja con **F2** (progreso = fases instrumentadas).

**Criterio de aceptación.** Subir un audio en la UI produce un run completo navegable sin usar la terminal.

---

## F5 · Doc técnica + roadmap, y actualización de docs existentes — P1 🔴 · objetivo #4

**Motivación.** La propuesta lista explícitamente *"actas, documentación técnica, roadmap y ADRs"*. Hoy solo se
generan **actas + ADRs** ([`generation/`](../src/meeting_forge/generation)). Faltan doc técnica y roadmap, y —más
importante— la capacidad de **actualizar documentos existentes** (no solo crear nuevos).

**Alcance.**
- Nuevos modos `technical-doc-update` y `roadmap-update` en `GenerationMode`
  ([`generation/schemas.py`](../src/meeting_forge/generation/schemas.py)).
- Prompts versionados: `prompts/generation/roadmap_v1.md`, `prompts/generation/tech_doc_v1.md`.
- Estrategias análogas a `AdrStrategy`/`ActaStrategy`.
- **Estrategia de actualización**: a partir de los docs recuperados por RAG, proponer un **diff** sobre el documento
  existente (no reescritura ciega). Mostrar el diff Markdown antes de publicar (liga con **F7/F11**).

**Módulos.** `generation/` (nuevas estrategias + schemas), `prompts/generation/`, integración en
`DocumentGenerator` y `run_e2e.py`, render de diffs en la UI.

**Criterio de aceptación.** Para una reunión con cambios de planificación, el sistema propone un diff sobre el
`ROADMAP.md` existente y un borrador de actualización de doc técnica, revisables en la UI.

---

## F6 · Endurecer RAG — P1 🟡 · objetivo #3

**Motivación.** Hacer el RAG fiable y depurable (recoge B1/B2/B7).

**Alcance.**
- Poda de chunks obsoletos al reindexar (**B2**) y comando `reindex` que sincronice (add/update/delete).
- Rutas include/exclude configurables y default sano (**B1**).
- Filtros opcionales por tipo de doc, carpeta o fecha en el retrieval.
- Logging de depuración del retrieval: score, ventana del transcript y chunk recuperado.
- Rangos de línea correctos en sub-chunks (**B7**) y clamp de score (**B8**).

**Módulos.** `rag/indexer.py`, `rag/vector_store.py`, `rag/retriever.py`, `rag/chunker.py`, `scripts/index_docs.py`.

**Criterio de aceptación.** Reindexar tras editar/borrar docs deja el índice consistente; los logs permiten ver por
qué se recuperó cada chunk.

---

## F7 · Endurecer integración Git — P1 🟡 · objetivo #5

**Motivación.** Publicar en un repo externo debe ser seguro y robusto (recoge B9/B10/B11/TD9).

**Alcance.**
- Guarda de **path traversal** al escribir en el repo destino (**TD9**).
- Detección de repo destino **sucio** (cambios sin commitear) antes de escribir.
- Manejo de **commit vacío** (**B10**).
- Separar disponibilidad de `gh` de **autenticación** real (**B11**); fallback manual (URL de compare / comando).
- Modo **`--dry-run`** que muestre qué se escribiría/commitearía sin tocar el repo.

**Módulos.** `git_integration/repo.py`, `git_integration/pr.py`, `git_integration/publisher.py`, `ui/app.py`.

**Criterio de aceptación.** Publicar con contenido idéntico, repo sucio o `gh` sin auth produce mensajes claros y no
deja el repo destino en estado inconsistente.

---

## F8 · Modo completamente automático opcional — P2 🟡 · objetivo #5

**Motivación.** La propuesta contempla un *"modo completamente automático opcional"*. Hoy todo pasa por validación humana.

**Alcance.**
- `AUTO_APPROVE_ENABLED=false` por defecto.
- **Raíles de seguridad**: solo ciertos tipos (p.ej. actas), solo PRs **draft**, repos en **allowlist**, y/o umbral
  de confianza.
- **Log de auditoría**: qué se auto-aprobó y por qué.
- Rollback / cierre automático de PR fácil si se detecta error.

**Módulos.** `validation/`, `git_integration/publisher.py`, `config.py`, `scripts/run_e2e.py`.

**Criterio de aceptación.** Con el modo activado y dentro de los raíles, una reunión genera y publica un PR draft de
acta sin intervención, con auditoría trazable.

---

## F9 · Robustez de ingesta de audio — P2 🔴 · objetivo #1

**Motivación.** La propuesta habla de reuniones reales **largas (~1h)**. [`ingestion/preprocessor.py`](../src/meeting_forge/ingestion/preprocessor.py)
es hoy un stub vacío.

**Alcance.**
- Implementar preprocesado: normalización de volumen, resampleo a 16 kHz, denoise opcional.
- Idioma configurable (**B4**).
- Diarización / etiquetado básico de hablantes (el schema ya tiene `speaker`).
- Transcripción por bloques para audios largos (memoria/tiempo).
- Fixture de audio pequeño para smoke test local.

**Módulos.** `ingestion/preprocessor.py`, `ingestion/transcriber.py`, `ingestion/schemas.py`.

**Criterio de aceptación.** Un audio largo y ruidoso produce una transcripción usable; existe un smoke test local
que no requiere descargar modelos pesados.

---

## F10 · Empaquetado y demo — P2 🟡 · demostrabilidad

**Motivación.** Que tutor/tribunal puedan ejecutar y reproducir el proyecto sin fricción.

**Alcance.**
- Entrypoints CLI en [`pyproject.toml`](../pyproject.toml): `meeting-forge-run`, `meeting-forge-index`,
  `meeting-forge-eval`.
- **Demo reproducible** con datos sintéticos/anonimizados + outputs esperados.
- Script de verificación de prerequisitos (ffmpeg, gh, API keys).
- Dockerfile opcional para UI y pipeline.
- Guía *"cómo reproducir la evaluación"* (liga con **F1**).

**Criterio de aceptación.** Un `README`/guía de demo permite, en pocos comandos, producir un run de ejemplo y la
tabla de métricas.

---

## F11 · Pulido de UX de validación — P2 🟢 · objetivos #5/#6

**Motivación.** Hoy, editar en el `text_area` y pulsar **"Aprobar"** (en vez de **"Guardar edición"**) **pierde la
edición**, porque `mark_approved` se llama sin `edited_content`
([`ui/app.py:317-329`](../src/meeting_forge/ui/app.py)).

**Alcance.**
- Unificar guardar+aprobar (o que "Aprobar" persista la edición en curso).
- Mostrar **diff** entre original y editado.
- Invalidar caché (`st.cache_data`) tras validar/publicar.
- Estados de error más accionables (Git, `gh`, RAG, docs faltantes).

**Módulos.** `ui/app.py`, `validation/store.py`.

**Criterio de aceptación.** El usuario no puede perder una edición por error; ve claramente qué cambió antes de publicar.

---

## F12 · Robustez de proveedores LLM (Ollama, retries, structured outputs) — P3 🟡 · transversal

**Motivación.** Cierra **B6** y mejora el argumento de privacidad/coste de la propuesta; además alimenta la
comparación de proveedores de la evaluación (**F1**).

**Alcance.**
- Implementar `OllamaProvider` (HTTP a `OLLAMA_BASE_URL`) — inferencia local/gratis.
- Validación de API keys al iniciar proveedor con error accionable.
- Retries con backoff para rate limits / errores temporales.
- Structured outputs estrictos donde el proveedor lo permita (OpenAI `json_schema`).

**Módulos.** `analysis/llm_client.py`, `config.py`, `.env.example`, `ARCHITECTURE.md`.

**Criterio de aceptación.** `LLM_PROVIDER=ollama` funciona end-to-end; las claves inválidas dan un error claro al
arrancar, no a mitad del pipeline.

---

## Notas de priorización

- El **bloque P0 (F1+F2+F3)** es el que más mueve la aguja del TFM: convierte el proyecto en algo **medible y
  reproducible**. Debe ir acompañado de **B1/B2** (índice limpio) para que las métricas de RAG sean válidas.
- **F5** y **F4** son las features que más completan la *visión* de la propuesta (doc técnica/roadmap y UI operativa).
- El orden global y el encaje con los arreglos de [`01-bugs-y-deuda-tecnica.md`](01-bugs-y-deuda-tecnica.md) está en
  [`00-orquestador.md`](00-orquestador.md).
