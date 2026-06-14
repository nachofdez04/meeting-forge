# Plan 01 · Bugs y deuda técnica

> Parte de [`planes/`](00-orquestador.md). Catálogo de problemas **ya existentes** en el código
> (bugs) y de **deuda técnica** (decisiones de diseño que conviene revisar). No incluye features
> nuevas — esas viven en [`02-features.md`](02-features.md).

## Cómo leer este documento

- **Prioridad**: `P0` (alto impacto / bloquea objetivos del TFM) → `P3` (cosmético / menor).
- **Esfuerzo**: 🟢 < 2 h · 🟡 medio día–1 día · 🔴 varios días.
- **Ubicación**: enlaces `archivo:línea` clicables.
- Cada ítem es **independiente**: ideal una rama/PR por ítem, con su test cuando aplique.

## Estado base verificado (2026-05-31)

Comprobado sobre el código real **en su estado actual** (posterior a la "Fase 5: Mejoras"):

| Comprobación | Resultado |
|---|---|
| `ruff check .` | ✅ All checks passed |
| `mypy src` | ✅ Success, no issues in 38 files |
| `pytest` | ✅ 189 passed, 2 skipped (integración) |
| Test flaky `test_sorted_most_recent_first` | ✅ Arreglado ([test_ui_loader.py:109](../tests/unit/test_ui_loader.py)) |
| CI + pre-commit | ✅ Existen (`.github/workflows/ci.yml`, `.pre-commit-config.yaml`) |

➡️ Los P0 de calidad del antiguo `MEJORAS_PROYECTO.md` (ruff, mypy, flaky, CI) **ya están resueltos**.
Este plan se centra en lo que sigue **realmente abierto**.

---

## Estado de implementación

> Actualizado: **2026-05-31**. Cambios en el árbol de trabajo (aún **sin commitear**).
> Gates tras los cambios: `ruff check` ✅ · `mypy src` ✅ (49 ficheros) · `pytest` ✅ **262 passed, 2 skipped**.

**✅ Completados — Fase A** (quick wins + RAG limpio + persistencia de datos)

- **B1** — `_collect_markdown` poda `.venv`/`.git`/`node_modules`/`data`/cachés y dirs ocultos vía `os.walk`
  ([rag/indexer.py](../src/meeting_forge/rag/indexer.py)). Test: [test_indexer.py](../tests/unit/test_indexer.py).
- **B2** — nuevo `ChromaVectorStore.delete_by_source()` + poda por source antes de reinsertar
  ([rag/vector_store.py](../src/meeting_forge/rag/vector_store.py), [rag/indexer.py](../src/meeting_forge/rag/indexer.py)). Test: [test_indexer.py](../tests/unit/test_indexer.py).
- **B3** — `validation.json` eliminado del control de versiones (`git rm`) y añadido a [`.gitignore`](../.gitignore).
- **B4** — `settings.whisper_language` (autodetección por defecto) + uso de `info.duration`
  ([config.py](../src/meeting_forge/config.py), [transcriber.py](../src/meeting_forge/ingestion/transcriber.py)).
- **B5** — `max_tokens` configurable en el cliente LLM ([analysis/llm_client.py](../src/meeting_forge/analysis/llm_client.py)).
- **B12** — README corregido + tests de integración con `skipif(RUN_INTEGRATION)`.
- **TD4** — código muerto eliminado ([templates.py](../src/meeting_forge/generation/templates.py), [chunker.py](../src/meeting_forge/rag/chunker.py)).
- **TD7** — `run_e2e` persiste `meeting_metadata` en `result.json` y la UI la relee al publicar (fecha/título
  correctos en rama y PR) ([run_e2e.py](../scripts/run_e2e.py), [ui/app.py](../src/meeting_forge/ui/app.py)). *(vía F3)*
- **TD8** — `run_e2e` persiste `retrieved_evidence` (texto + score) expuesta por `extractor.last_context`
  ([extractor.py](../src/meeting_forge/analysis/extractor.py), [run_e2e.py](../scripts/run_e2e.py)). *(vía F3)*
- **TD11** — CI con matriz `{3.11,3.12,3.13} × {ubuntu,windows}` + `mypy` en pre-commit
  ([ci.yml](../.github/workflows/ci.yml), [`.pre-commit-config.yaml`](../.pre-commit-config.yaml)).
- **TD12** — `uv.lock` designorado para versionarlo ([`.gitignore`](../.gitignore)). *(Falta `git add` + commit del lockfile.)*

**✅ Completados — Fase B** (robustez)

- **TD1** — `GeneratedDocView` movido a [generation/schemas.py](../src/meeting_forge/generation/schemas.py);
  `validation/` y `git_integration/` ya **no importan `ui/`** (rota la inversión de capas). La UI lo re-exporta.
- **B7** — sub-chunks con rangos de línea propios al dividir por tamaño ([rag/chunker.py](../src/meeting_forge/rag/chunker.py)). Test en [test_chunker.py](../tests/unit/test_chunker.py).
- **B8** — score de retrieval con clamp a [0,1] ([rag/vector_store.py](../src/meeting_forge/rag/vector_store.py)).
- **TD5** — try/except por decisión en `generate_per_decision` (un fallo no tira el resto de ADRs) ([adr_strategy.py](../src/meeting_forge/generation/adr_strategy.py)).
- **B9** — git con locale `C` para que las comprobaciones por texto no dependan del idioma ([repo.py](../src/meeting_forge/git_integration/repo.py)).
- **B10** — manejo de **commit vacío** con mensaje claro ([repo.py](../src/meeting_forge/git_integration/repo.py)). Test en [test_git_integration_repo.py](../tests/unit/test_git_integration_repo.py).
- **B11** — `is_gh_authenticated()` separado de `is_gh_available()`; la UI distingue "no instalado" de "no autenticado" ([pr.py](../src/meeting_forge/git_integration/pr.py), [ui/app.py](../src/meeting_forge/ui/app.py)).
- **TD9** — guardas de **path-traversal** al escribir en el repo destino y al leer evidencia ([repo.py](../src/meeting_forge/git_integration/repo.py), [ui/evidence.py](../src/meeting_forge/ui/evidence.py)). Test en [test_git_integration_repo.py](../tests/unit/test_git_integration_repo.py).
- **TD3** — lógica de marcadores unificada en `rewrite_marker_text()` ([citations.py](../src/meeting_forge/generation/citations.py)); `adr_strategy` ya no duplica regex ni `_remap_markers`.
- **TD6** — `AdrStrategy` memoiza la prosa por decisión: ADR por-decisión + consolidado cuesta **N** llamadas LLM, no 2N ([adr_strategy.py](../src/meeting_forge/generation/adr_strategy.py)).
- **B6** — `OllamaProvider` implementado (API compatible con OpenAI vía `OLLAMA_BASE_URL/v1`) ([llm_client.py](../src/meeting_forge/analysis/llm_client.py)). Test de selección en [test_llm_client.py](../tests/unit/test_llm_client.py).
- **TD2** — importar el paquete ya **no crea directorios**: `model_post_init` retirado, dirs creados vía
  `ensure_data_dirs()` solo en los entrypoints ([config.py](../src/meeting_forge/config.py), [run_e2e.py](../scripts/run_e2e.py), [index_docs.py](../scripts/index_docs.py)). Test en [test_config.py](../tests/unit/test_config.py).
- **TD13** — `except Exception` silenciosos acotados a `(OSError, ValueError)` y logueados
  ([ui/loader.py](../src/meeting_forge/ui/loader.py), [validation/store.py](../src/meeting_forge/validation/store.py), [git_integration/publisher.py](../src/meeting_forge/git_integration/publisher.py)).

**🟡 Parcial**

- **TD10** — tests añadidos: indexer (B1/B2 + sync F6), `_strip_markdown_fences`, telemetría, métricas de evaluación,
  split de chunker (B7), path-traversal, commit vacío, repo limpio/sucio, selección de proveedor, `ensure_data_dirs`,
  `build_compare_url`. Pendiente: transcriber.

**⬜ Pendientes**: ninguno — todos los bugs (B1–B12) y la deuda (TD1–TD13) catalogados están **resueltos**
(TD10 con cobertura ampliada; solo falta el test del transcriptor).

---

## Resumen (tabla)

| ID | Título | Tipo | Prioridad | Esfuerzo |
|---|---|---|---|---|
| B1 | El indexer arrastra `.venv` y ruido del repo | Bug | **P0** | 🟡 |
| B2 | Chunks obsoletos nunca se eliminan al reindexar | Bug | **P0** | 🟡 |
| B3 | `validation.json` stray trackeado en la raíz | Bug | **P0** | 🟢 |
| B4 | Transcriptor con idioma fijo y duración imprecisa | Bug | P1 | 🟢 |
| B5 | `max_tokens=4000` hardcoded ignora la config | Bug | P1 | 🟢 |
| B6 | Ollama anunciado pero no implementado | Bug | P1 | 🟡 |
| B7 | El split por tamaño pierde precisión de líneas | Bug | P1 | 🟡 |
| B8 | `score = 1.0 - dist` puede ser negativo | Bug | P2 | 🟢 |
| B9 | Detección de "no upstream" dependiente del idioma | Bug | P2 | 🟢 |
| B10 | Sin manejo de "commit vacío" | Bug | P2 | 🟢 |
| B11 | `is_gh_available` comprueba versión, no auth | Bug | P2 | 🟢 |
| B12 | Comando de tests de integración del README inválido | Bug (doc) | P3 | 🟢 |
| TD1 | Violación de capas: dominio depende de la UI | Deuda | P1 | 🟡 |
| TD2 | Singleton `settings` con efectos en import | Deuda | P1 | 🟡 |
| TD3 | Lógica de marcadores duplicada | Deuda | P2 | 🟢 |
| TD4 | Código muerto | Deuda | P2 | 🟢 |
| TD5 | Granularidad de fallo en ADRs | Deuda | P2 | 🟢 |
| TD6 | El ADR consolidado re-llama al LLM (2N llamadas) | Deuda | P2 | 🟡 |
| TD7 | `run_e2e.py` no persiste la metadata de la reunión | Deuda | **P0/P1** | 🟡 |
| TD8 | Evidencia RAG no persistida con el resultado | Deuda | P1 | 🟡 |
| TD9 | Sin guardas de path traversal al escribir/leer | Deuda | P2 | 🟢 |
| TD10 | Huecos de tests | Deuda | P1 | 🟡 |
| TD11 | CI mono-plataforma/mono-Python | Deuda | P2 | 🟢 |
| TD12 | `uv.lock` no versionado | Deuda | P1 | 🟢 |
| TD13 | `except Exception` amplio en varios puntos | Deuda | P3 | 🟢 |

---

## Bugs

### B1 · El indexer arrastra `.venv` y ruido del repo — **P0** 🟡

**Impacto.** Destroza la calidad del retrieval (precisión), que es el corazón del RAG del TFM.

**Dónde.** [`scripts/index_docs.py:49`](../scripts/index_docs.py) añade `settings.project_root` a las rutas;
[`rag/indexer.py:68-87` `_collect_markdown`](../src/meeting_forge/rag/indexer.py) hace `path.rglob("*.md")`
**sin ninguna exclusión**.

**Por qué falla.** Al indexar el root del repo, `rglob` desciende a `.venv/Lib/site-packages/**/*.md`
(cientos de model cards y READMEs de dependencias), `.pytest_cache/README.md`, `MEJORAS_PROYECTO.md`,
`ARCHITECTURE.md`, etc. El índice queda dominado por ruido y el retriever devuelve chunks irrelevantes.

**Arreglo propuesto.**
- Añadir una lista de exclusión configurable (dirs ocultos + `.venv`, `.git`, `node_modules`, `data`,
  `.pytest_cache`, `build`, `dist`, `*.egg-info`) en `_collect_markdown`.
- Mejor aún: cambiar el **default** para que `index_docs.py` indexe solo `settings.docs_path` (+ rutas `--path`),
  y que indexar el repo entero sea opt-in explícito (`--include-repo`).
- Exponer `settings.index_exclude_globs` para personalizar.

**Test.** `test_indexer.py`: fs falso con `docs/a.md` + `.venv/x.md`; asertar que solo se recoge `docs/a.md`.

---

### B2 · Chunks obsoletos nunca se eliminan al reindexar — **P0** 🟡

**Impacto.** El retrieval devuelve contenido desactualizado; rompe la "trazabilidad" prometida en la propuesta.

**Dónde.** [`rag/indexer.py`](../src/meeting_forge/rag/indexer.py) inserta con `upsert` usando
`chunk_id = sha1(source_path:line_start-line_end:text)` ([`chunker.py:28`](../src/meeting_forge/rag/chunker.py)).

**Por qué falla.** Al editar un documento, cambian el texto y los rangos → nuevo `chunk_id`. El `upsert` añade
el nuevo chunk pero **no borra** el viejo (con hash distinto). Si se renombra o borra el fichero, todos sus
chunks quedan huérfanos para siempre.

**Arreglo propuesto.**
- En el indexer, antes de reindexar un fichero, borrar de Chroma todos los chunks con `metadata.source_path == rel`
  (Chroma soporta `delete(where={"source_path": rel})`).
- Alternativa más completa: un `sync(paths)` que calcule el conjunto de `chunk_id` esperados y pode los que ya
  no se producen (full reconcile). Liga con **F6**.

**Test.** Indexar un doc, editarlo, reindexar; asertar que `count()` no crece indefinidamente y que el chunk viejo desaparece.

---

### B3 · `validation.json` stray trackeado en la raíz — **P0** 🟢

**Impacto.** Artefacto accidental versionado; confunde y contradice la arquitectura.

**Dónde.** [`validation.json`](../validation.json) en la raíz, **git-trackeado** (`git ls-files` lo lista), con
registros falsos (`"0.md"`..`"3.md"`). Según [ARCHITECTURE.md](../ARCHITECTURE.md) el estado HITL vive en
`data/outputs/<meeting>/validation.json` (ya gitignored vía `data/outputs/*`).

**Arreglo propuesto.** `git rm validation.json` (es un commit accidental). Opcional: añadir `/validation.json`
a [`.gitignore`](../.gitignore) para evitar recommitearlo desde la raíz.

---

### B4 · Transcriptor con idioma fijo y duración imprecisa — P1 🟢

**Impacto.** Reuniones no-español mal transcritas; `duration_seconds` ligeramente incorrecta (afecta a métricas de latencia/coste por minuto).

**Dónde.** [`ingestion/transcriber.py:43`](../src/meeting_forge/ingestion/transcriber.py) fija `language="es"`;
[`transcriber.py:57`](../src/meeting_forge/ingestion/transcriber.py) calcula `duration = segments[-1].end`.

**Arreglo propuesto.**
- Añadir `settings.whisper_language: str | None = None` (None = auto-detect de faster-whisper) y pasarlo a `transcribe`.
- Usar `info.duration` (lo expone faster-whisper) en vez del fin del último segmento.

---

### B5 · `max_tokens=4000` hardcoded ignora `settings.generation_max_tokens` — P1 🟢

**Impacto.** Cambiar `GENERATION_MAX_TOKENS` en `.env` no tiene ningún efecto (sorpresa de configuración).

**Dónde.** [`analysis/llm_client.py:57`](../src/meeting_forge/analysis/llm_client.py) (Anthropic) y
[`llm_client.py:100`](../src/meeting_forge/analysis/llm_client.py) (OpenAI) fijan `max_tokens=4000`.

**Arreglo propuesto.** Aceptar `max_tokens: int | None` en `complete`/`complete_structured`; default desde
`settings.generation_max_tokens`. El generador puede pasar el suyo explícitamente.

---

### B6 · Ollama anunciado pero no implementado — P1 🟡

**Impacto.** Promesa rota: la config y la doc ofrecen un proveedor que revienta en runtime.

**Dónde.** [`config.py:31`](../src/meeting_forge/config.py) permite `llm_provider="ollama"`;
[`.env.example:17,22,27`](../.env.example) lo documenta; pero
[`llm_client.py:142`](../src/meeting_forge/analysis/llm_client.py) lanza `ValueError("...no está implementado en Fase 0")`.

**Arreglo propuesto.** Dos caminos (elegir uno):
1. **Implementarlo** (ver **F12**): `OllamaProvider` con cliente HTTP a `OLLAMA_BASE_URL`.
2. **Retirar la promesa** temporalmente: quitar `"ollama"` del `Literal`, comentar las vars en `.env.example`
   y la fila en ARCHITECTURE, hasta que exista.

---

### B7 · El split por tamaño pierde precisión de líneas en las citas — P1 🟡

**Impacto.** Degrada la provenance (argumento central del TFM): las citas de secciones grandes apuntan a toda la
sección en lugar de a las líneas concretas.

**Dónde.** [`rag/chunker.py:143` `_maybe_split_by_size`](../src/meeting_forge/rag/chunker.py) reparte el rango de
líneas **completo de la sección** a cada sub-chunk. Además la clave de dedupe `path:line_start-line_end`
([`extractor.py:162`](../src/meeting_forge/analysis/extractor.py),
[`citations.py:27`](../src/meeting_forge/generation/citations.py)) colapsa sub-chunks distintos de una sección
grande en una sola `SourceRef`.

**Arreglo propuesto.** Calcular rangos de línea aproximados por sub-chunk contando saltos de línea consumidos en
cada slice (acumulador sobre el texto original). No hace falta exactitud perfecta, pero sí distinguir sub-chunks.

**Test.** Sección de 3000 chars con varias líneas → sub-chunks con rangos de línea distintos y crecientes.

---

### B8 · `score = 1.0 - dist` puede ser negativo — P2 🟢

**Impacto.** Semántica de score laxa; molestará al fijar umbrales y al reportar precision@k.

**Dónde.** [`rag/vector_store.py:96`](../src/meeting_forge/rag/vector_store.py). Con distancia coseno ∈ [0, 2],
el score cae en [-1, 1].

**Arreglo propuesto.** `score = max(0.0, 1.0 - dist)` (o mapear explícitamente), y documentar el rango.

---

### B9 · Detección de "no upstream" en `git pull` dependiente del idioma — P2 🟢

**Impacto.** En un git con locale no inglés, `pull()` puede tratar un fallo legítimo como esperado, o viceversa.

**Dónde.** [`git_integration/repo.py:80`](../src/meeting_forge/git_integration/repo.py) busca el string
`"no tracking information"` en `stderr`.

**Arreglo propuesto.** Forzar `LC_ALL=C`/`LANG=C` en el `env` de `_run` (para mensajes estables), o comprobar de
forma estructural si la rama tiene upstream (`git rev-parse --abbrev-ref @{u}`) antes de hacer pull.

---

### B10 · Sin manejo de "commit vacío" — P2 🟢

**Impacto.** Si el contenido aprobado es idéntico al ya existente en el repo destino, `git commit` falla y la
publicación entera aborta con un error poco claro.

**Dónde.** [`git_integration/repo.py:99` `add_and_commit`](../src/meeting_forge/git_integration/repo.py).

**Arreglo propuesto.** Tras `git add`, comprobar `git diff --cached --quiet`; si no hay cambios, devolver un
resultado "nada que publicar / ya está actualizado" en vez de lanzar error. Liga con **F7**.

---

### B11 · `is_gh_available` comprueba versión, no autenticación — P2 🟢

**Impacto.** Bajo (el publisher ya captura el fallo de `create_pr` y continúa con commit+push). Pero el mensaje de
la UI dice "no disponible o no autenticado" cuando solo se ha comprobado la versión.

**Dónde.** [`git_integration/pr.py:19`](../src/meeting_forge/git_integration/pr.py) solo ejecuta `gh --version`.

**Arreglo propuesto.** Añadir `gh auth status` como check separado; en la UI distinguir "no instalado" de "no
autenticado" y ofrecer fallback (imprimir URL de compare / comando `gh pr create`). Liga con **F7**.

---

### B12 · Comando de tests de integración del README es inválido — P3 🟢 (doc)

**Impacto.** Quien siga el README para correr integración obtiene un error.

**Dónde.** [`README.md:129`](../README.md): `uv run pytest -m integration --no-skip`. `--no-skip` no es un flag de
pytest. Los tests usan `@pytest.mark.skip` (skip duro).

**Arreglo propuesto.** Corregir la doc; y/o convertir los `skip` en `skipif` condicionados a una variable de
entorno (p.ej. `RUN_INTEGRATION=1`) para que `-m integration` realmente pueda ejecutarlos.

---

## Deuda técnica

### TD1 · Violación de capas: el dominio depende de la UI — P1 🟡

**Impacto.** Acoplamiento invertido y ciclo de imports; dificulta tests y reutilización (p.ej. publicar sin Streamlit instalado).

**Dónde.** [`validation/store.py:9`](../src/meeting_forge/validation/store.py) y
[`git_integration/publisher.py:12`](../src/meeting_forge/git_integration/publisher.py) importan `GeneratedDocView`
desde `..ui.loader`; a su vez [`ui/loader.py:117`](../src/meeting_forge/ui/loader.py) importa el publisher de forma
**perezosa** (import dentro de función + `TYPE_CHECKING`) precisamente para romper el ciclo.

**Arreglo propuesto.** Mover `GeneratedDocView` (y cualquier view-model compartido) a un módulo de dominio sin UI
—p.ej. `generation/schemas.py` o un nuevo `meeting_forge/core/`— y que la UI importe desde ahí. Elimina el ciclo y
los imports perezosos.

---

### TD2 · Singleton `settings` con efectos secundarios en import — P1 🟡

**Impacto.** Importar el paquete crea directorios en disco; import no puro, sorpresas en tests y herramientas.

**Dónde.** [`config.py:94`](../src/meeting_forge/config.py) hace `settings = Settings()` a nivel de módulo, y
[`config.py:87` `model_post_init`](../src/meeting_forge/config.py) crea `data/{raw,transcripts,outputs}` + chromadb.

**Arreglo propuesto.** Pasar a `get_settings()` con `functools.lru_cache`, y crear directorios solo en los
entrypoints (`run_e2e.py`, `index_docs.py`, UI) o de forma perezosa al primer uso. Mantener compatibilidad con un
alias `settings` si se quiere migración gradual.

---

### TD3 · Lógica de marcadores duplicada — P2 🟢

**Dónde.** [`generation/adr_strategy.py` `_remap_markers`](../src/meeting_forge/generation/adr_strategy.py) es casi
idéntica a [`generation/citations.py` `rewrite_markers`](../src/meeting_forge/generation/citations.py); y
`_MARKER_RE` / `_CODE_FENCE_RE` están repetidos en `extractor.py`, `citations.py` y `adr_strategy.py`.

**Arreglo propuesto.** Unificar en `citations.py` una función parametrizable (variante por-registry y variante por
mapeo `local→global`) y exportar las regex compartidas.

---

### TD4 · Código muerto — P2 🟢

**Dónde.**
- [`generation/templates.py:46-60`](../src/meeting_forge/generation/templates.py): `_ADR_CONSOLIDATED_HEADER` y
  `_ADR_CONSOLIDATED_SECTION` no se usan (el ADR consolidado se construye inline en `adr_strategy.py`).
- [`rag/chunker.py:139-140`](../src/meeting_forge/rag/chunker.py): `current_lines`/`current_start` existen solo para
  "callar" al linter (`_ = (current_lines, current_start)`).

**Arreglo propuesto.** Eliminar ambos. (No los detecta ruff porque son constantes de módulo / asignaciones "usadas".)

---

### TD5 · Granularidad de fallo en ADRs — P2 🟢

**Impacto.** Un único fallo del LLM tira **todos** los ADRs del modo `adr-per-decision`.

**Dónde.** [`generation/adr_strategy.py:116` `generate_per_decision`](../src/meeting_forge/generation/adr_strategy.py)
itera sin try/except por decisión; el `DocumentGenerator` solo captura a nivel de modo
([`generator.py:60-74`](../src/meeting_forge/generation/generator.py)).

**Arreglo propuesto.** Envolver cada decisión en try/except; emitir los ADRs que sí salen y loguear los fallidos.

---

### TD6 · El ADR consolidado re-llama al LLM (2N llamadas si ambos modos) — P2 🟡

**Impacto.** Coste y latencia x2 cuando se habilitan `adr-per-decision` **y** `adr-consolidated` (mismas N decisiones, 2N llamadas).

**Dónde.** [`generation/adr_strategy.py`](../src/meeting_forge/generation/adr_strategy.py): `generate_per_decision`
y `generate_consolidated` llaman a `_call_llm` por separado para las mismas decisiones.

**Arreglo propuesto.** Generar el `_RawADR` por decisión **una vez** y reutilizarlo en ambos ensamblados (cachear
por `decision` o reestructurar el generador para compartir la pasada). Relevante para las métricas de coste (**F1**).

---

### TD7 · `run_e2e.py` no persiste la metadata de la reunión — **P0/P1** 🟡

**Impacto.** La UI no puede reconstruir fecha/título → las ramas y PRs pierden la fecha y el título real.

**Dónde.** [`scripts/run_e2e.py:160`](../scripts/run_e2e.py) guarda en `result.json` solo
`provider/whisper_model/rag_enabled/embedding_model`. La UI entonces hace
`MeetingMetadata(meeting_id=..., title=meeting_id, date=None, source_audio=None)`
([`ui/app.py:375`](../src/meeting_forge/ui/app.py)).

**Arreglo propuesto.** Persistir el `MeetingMetadata` usado en generación (fecha/título/source_audio) dentro de
`result.json` y releerlo en la UI/publisher. Se formaliza en **F3**.

---

### TD8 · Evidencia RAG no persistida con el resultado — P1 🟡

**Impacto.** La evidencia depende de que los ficheros fuente sigan intactos en el mismo path; cualquier métrica
sobre evidencia deja de ser reproducible.

**Dónde.** Solo se guarda `SourceRef` (path+líneas); la UI relee el fichero en vivo
([`ui/evidence.py`](../src/meeting_forge/ui/evidence.py)).

**Arreglo propuesto.** Persistir, junto al resultado, el **texto exacto** del chunk recuperado + su `score` (y
ventana/idx). Habilita evidencia estable y observabilidad. Se formaliza en **F2/F3**.

---

### TD9 · Sin guardas de path traversal al escribir/leer — P2 🟢 (defensivo)

**Impacto.** Riesgo práctico bajo (entradas slugificadas/derivadas), pero escribir en un repo externo sin guarda es
mala práctica.

**Dónde.** [`git_integration/repo.py:88` `write_files`](../src/meeting_forge/git_integration/repo.py) hace
`repo / rel_path` sin validar; [`ui/evidence.py:42`](../src/meeting_forge/ui/evidence.py) hace `base_dir / source_path`.

**Arreglo propuesto.** Resolver (`.resolve()`) y asertar que el destino queda dentro de la base
(`target.is_relative_to(base)`), rechazando `..` y rutas absolutas. Liga con **F7**.

---

### TD10 · Huecos de tests — P1 🟡

**Impacto.** Lógica crítica sin red de seguridad; el bug **B1** ni siquiera estaba cubierto.

**Sin tests.** [`rag/indexer.py`](../src/meeting_forge/rag/indexer.py),
[`ingestion/transcriber.py`](../src/meeting_forge/ingestion/transcriber.py),
parseo de [`analysis/llm_client.py`](../src/meeting_forge/analysis/llm_client.py) (`_strip_markdown_fences`),
split de [`rag/chunker.py`](../src/meeting_forge/rag/chunker.py). Coverage ~70 %.

**Arreglo propuesto.** Tests unitarios de la lógica pura:
- `_collect_markdown` con fs falso (incluye exclusiones de B1).
- `_strip_markdown_fences` con varios fences.
- `_maybe_split_by_size` (rangos de línea de B7).
- Transcriptor con un `WhisperModel` mockeado (sin descargar modelo).

---

### TD11 · CI mono-plataforma / mono-Python — P2 🟢

**Impacto.** El proyecto declara soporte 3.11–3.13 y se desarrolla en Windows, pero CI solo prueba ubuntu+3.11 (el
flaky histórico era específico de Windows).

**Dónde.** [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).

**Arreglo propuesto.** Matriz `{3.11, 3.12, 3.13} × {ubuntu-latest, windows-latest}`. Añadir `mypy` al
[`.pre-commit-config.yaml`](../.pre-commit-config.yaml).

---

### TD12 · `uv.lock` no versionado — P1 🟢

**Impacto.** Reproducibilidad: para una defensa de TFM, el tribunal debería poder reproducir el entorno exacto.

**Dónde.** Ignorado en [`.gitignore:17`](../.gitignore) (confirmado: `git check-ignore uv.lock` matchea).

**Arreglo propuesto.** Quitar `uv.lock` del `.gitignore` y commitearlo. Documentar la decisión (idealmente como un
ADR del propio repo, encajando con la temática del proyecto).

---

### TD13 · `except Exception` amplio en varios puntos — P3 🟢

**Impacto.** Degradación elegante correcta, pero se pierde el detalle del error al depurar.

**Dónde.** [`generator.py:69`](../src/meeting_forge/generation/generator.py),
[`run_e2e.py:220`](../scripts/run_e2e.py), [`ui/loader.py:63`](../src/meeting_forge/ui/loader.py),
load de validation/publish.

**Arreglo propuesto.** Mantener la captura amplia donde aporta robustez, pero loguear tipo+mensaje de forma
consistente (`logger.exception(...)` o `logger.warning("...: {e}", e=exc)`).

---

## Quick wins (hacer primero, < 1 día en total)

`B3` · `B4` · `B5` · `TD4` · `B12` · `TD12` · (matriz CI de `TD11`).
Todos pequeños, sin tocar arquitectura, y dejan el repo más limpio y reproducible de inmediato.

## Orden sugerido (resumen)

1. **Quick wins** (arriba).
2. **P0 de RAG**: `B1` → `B2` (índice limpio: prerequisito para que la evaluación del RAG tenga sentido).
3. **P0/P1 de datos**: `TD7` + `TD8` (persistir metadata y evidencia) — habilitan la evaluación y la observabilidad.
4. **P1 restantes**: `TD1`, `TD2`, `B6`, `B7`, `TD10`.
5. **P2/P3**: el resto, oportunista por PR.

> El encaje de estos arreglos con las features y las fases del TFM está en
> [`00-orquestador.md`](00-orquestador.md).
