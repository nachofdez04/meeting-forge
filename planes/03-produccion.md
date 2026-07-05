# Plan 03 · Camino a producción

> Parte de [`planes/`](00-orquestador.md). Catálogo de lo que **falta para que MeetingForge sea
> desplegable y operable de forma profesional** por un equipo real. No repite bugs ya corregidos
> ([01](01-bugs-y-deuda-tecnica.md)) ni features ya implementadas ([02](02-features.md)): parte del
> estado actual (Fases A/B/C completadas + 9 bugs corregidos el 2026-07-05) y mira hacia delante.

## Cómo leer este documento

- **Prioridad**: `P0` (bloquea el despliegue ante usuarios) → `P3` (futuro deseable).
- **Esfuerzo**: 🟢 < 2 h · 🟡 medio día–1 día · 🔴 varios días.
- Cada ítem es **independiente**: una rama/PR por ítem, con su test cuando aplique.
- Prefijo **PROD-n** para distinguirlos de B/TD/F/M de los planes anteriores.

## Definición de "producción" para este proyecto

Escenario objetivo realista (y defendible en la memoria): **despliegue interno para un equipo**
(5–20 personas) que sube audios de sus reuniones, valida documentos y publica a su repo de docs.
NO es objetivo: SaaS multi-tenant, transcripción en streaming, alta disponibilidad.

## Estado base verificado (2026-07-05)

| Comprobación | Resultado |
|---|---|
| `pytest` | ✅ 294 passed |
| `ruff check` / `mypy src --strict` | ✅ / ✅ |
| Dockerfile + .dockerignore | ✅ Existen (M3) — sin healthcheck ni usuario no-root |
| CI (lint + mypy + tests, matriz 3.11–3.13 × ubuntu/windows) | ✅ — sin cobertura, formato ni auditoría |
| LICENSE | ❌ No existe (pyproject declara MIT) |
| Autenticación UI / límites de subida | ❌ No hay |
| Timeouts en subprocesos (git, gh, ffmpeg) | ❌ No hay |
| Concurrencia (2 pipelines a la vez) | ❌ Sin protección |
| Tope de coste / transcripts largos | ❌ Sin límites |
| Retención/borrado de datos | ❌ No hay |

---

## Roadmap por hitos

| Hito | Ítems | Resultado demostrable |
|---|---|---|
| **H1 — Desplegable con seguridad** (P0) | PROD-1 … PROD-6 | Un equipo puede usarlo sin riesgo de coste desbocado, cuelgues ni acceso anónimo |
| **H2 — Operable y observable** (P1) | PROD-7 … PROD-13 | Se puede diagnosticar, medir y mantener sin tocar código |
| **H3 — Producto redondo** (P2) | PROD-14 … PROD-20 | UX completa: gestionar reuniones, speakers con nombre, RAG que aprende |
| **Futuro** (P3) | PROD-21 … | API programática, multi-usuario real |

---

# Hito 1 — Desplegable con seguridad (P0)

## PROD-1 · Autenticación y límites en la UI — P0 🟡

**Problema**: la UI Streamlit no tiene autenticación y el Dockerfile la expone en `0.0.0.0:8501`.
Cualquiera con acceso de red puede subir audios (disparando coste LLM), aprobar documentos y
**publicar a Git**. Tampoco hay límite de tamaño de subida explícito ni `.streamlit/config.toml`.

**Qué hacer**:
- Añadir `.streamlit/config.toml` con `server.maxUploadSize` (p.ej. 500 MB), tema y
  `browser.gatherUsageStats = false`.
- Gate de acceso mínimo en [ui/app.py](../src/meeting_forge/ui/app.py) `main()`: password compartida
  vía `UI_PASSWORD` en settings (comparación con `hmac.compare_digest`, formulario `st.text_input
  type="password"`, flag en `st.session_state`). Si `UI_PASSWORD` está vacío → sin gate (dev).
- Documentar en README el despliegue recomendado detrás de reverse proxy (Caddy/nginx) con TLS y
  auth real (basic/OIDC) para producción; la password de la app es defensa en profundidad, no
  sustituto.

**Aceptación**: con `UI_PASSWORD` definida, ninguna pestaña se renderiza sin autenticarse; test
unitario del helper de comparación; subida > límite rechazada por Streamlit.

## PROD-2 · Timeouts en todos los subprocesos y clientes — P0 🟡

**Problema**: [git_integration/repo.py](../src/meeting_forge/git_integration/repo.py) `_run()`,
[pr.py](../src/meeting_forge/git_integration/pr.py) `create_pr()` y
[preprocessor.py](../src/meeting_forge/ingestion/preprocessor.py) ejecutan `subprocess.run` **sin
timeout**: un `git push` contra un remote colgado o un ffmpeg atascado congelan la UI/CLI para
siempre (el spinner de "Publicando en Git..." no termina nunca). Los clientes LLM usan los timeouts
por defecto del SDK, no configurables.

**Qué hacer**:
- `_run(args, cwd, check, timeout=settings.git_timeout_s)` (default 120 s; clone/push 600 s), y
  capturar `subprocess.TimeoutExpired` → `GitOperationError` legible. Igual en `create_pr` y
  `preprocess_audio` (ffmpeg, p.ej. 10 min).
- Settings nuevos: `GIT_TIMEOUT_S`, `FFMPEG_TIMEOUT_S`, `LLM_TIMEOUT_S` (pasado a
  `Anthropic(timeout=...)` / `OpenAI(timeout=...)` en
  [llm_client.py](../src/meeting_forge/analysis/llm_client.py)).

**Aceptación**: test que simula un comando lento (script que duerme) y verifica el error claro;
ningún `subprocess.run` del paquete sin `timeout`.

## PROD-3 · Control de concurrencia del pipeline — P0 🟡

**Problema**: dos ejecuciones simultáneas (dos pestañas de la UI, o CLI + UI) escriben sin
coordinación en `data/outputs/<meeting>/` y en ChromaDB. El mismo audio dos veces → `result.json`
corrupto a medias o validación inconsistente.

**Qué hacer**:
- Lock por reunión en [pipeline.py](../src/meeting_forge/pipeline.py): fichero
  `out_dir/.processing.lock` creado con `os.open(..., O_CREAT | O_EXCL)` (atómico, stdlib, sin
  dependencia nueva) + PID/timestamp dentro; liberar en `finally`; locks huérfanos (> N horas o PID
  muerto) se consideran expirados con warning.
- Si el lock existe → `MeetingAlreadyProcessingError` que la UI muestra como info ("esta reunión ya
  se está procesando") y el CLI como exit code ≠ 0.
- La UI deshabilita el botón «Procesar» mientras haya un run en curso en la sesión.

**Aceptación**: test de doble llamada concurrente (segunda falla limpio); lock liberado tras éxito
y tras excepción.

## PROD-4 · Presupuesto LLM y transcripts largos — P0 🔴

**Problema**: [extractor.py](../src/meeting_forge/analysis/extractor.py) mete el transcript
**entero** en un prompt. Una reunión de 2 h puede desbordar la ventana de contexto (error críptico
del proveedor) o costar mucho más de lo esperado. No hay tope de gasto: un bucle de reintentos +
documentos + ADRs puede acumular coste sin freno.

**Qué hacer** (dos sub-ítems, separables):
1. **Guardarraíl de tamaño** 🟡: estimar tokens del prompt (`len(texto)//4` es suficiente);
   setting `EXTRACTION_MAX_INPUT_TOKENS`. Si se supera → estrategia **map-reduce**: trocear el
   transcript por bloques de N caracteres (reutilizar `_sliding_windows` de
   [retriever.py](../src/meeting_forge/rag/retriever.py) sin solape), extraer insights por bloque y
   fusionar (concatenar decisiones/tareas, deduplicar por similitud de título con el Jaccard de
   [evaluation/metrics.py](../src/meeting_forge/evaluation/metrics.py), re-resumir los summaries).
2. **Tope de coste por run** 🟡: setting `MAX_RUN_COST_USD` (0 = sin límite). El
   [TelemetryCollector](../src/meeting_forge/observability.py) ya conoce el coste acumulado:
   añadir `collector.check_budget()` que lance `BudgetExceededError`; los proveedores la llaman
   tras registrar cada llamada. El pipeline la captura → persiste resultado parcial (mismo
   mecanismo que BUG-2) con `error.phase = "budget"`.

**Aceptación**: tests puros del troceo+fusión y del budget con collector fake; una reunión larga
sintética produce insights sin error de contexto.

## PROD-5 · Retención y borrado de datos (RGPD) — P0 🟡

**Problema**: los audios y transcripciones son **datos personales** (voces, nombres, decisiones).
Hoy se acumulan para siempre en `data/raw/` y `data/outputs/` sin forma de borrarlos salvo a mano.
Para un despliegue real (y para la memoria del TFM) hace falta un ciclo de vida explícito.

**Qué hacer**:
- Comando `meeting-forge purge <meeting-id>` en [cli.py](../src/meeting_forge/cli.py): borra
  `data/outputs/<id>/`, el audio original en `data/raw/` (incluido el derivado `*_pre16k.wav`) y
  el transcript. Con `--older-than 90` borra reuniones con `mtime` anterior; `--dry-run` lista.
- Setting `KEEP_RAW_AUDIO: bool = True`: si es `False`, el pipeline borra el audio tras transcribir
  (el transcript basta para todo lo posterior).
- Sección "Datos y privacidad" en el README: qué se guarda, dónde, cómo purgarlo, y que el
  transcript viaja al proveedor LLM configurado (con Ollama todo queda en local — argumento fuerte
  del TFM).

**Aceptación**: tests de purge (por id, por antigüedad, dry-run); `KEEP_RAW_AUDIO=false` deja
`data/raw/` limpio tras un run.

## PROD-6 · Legal y versionado del producto — P0 🟢

**Problema**: `pyproject.toml` declara `license = MIT` pero **no existe fichero `LICENSE`** (sin él,
legalmente no hay licencia). No hay `--version` en el CLI ni CHANGELOG: imposible saber qué versión
corre un despliegue.

**Qué hacer**:
- Añadir `LICENSE` (texto MIT, año y autor).
- `meeting-forge --version` (callback de Typer leyendo `importlib.metadata.version`).
- `CHANGELOG.md` (formato *Keep a Changelog*) arrancando en `0.1.0` con lo hecho hasta hoy; a
  partir de aquí, tag `vX.Y.Z` por release.

**Aceptación**: `meeting-forge --version` imprime la versión del paquete; LICENSE presente.

---

# Hito 2 — Operable y observable (P1)

## PROD-7 · Logs persistentes con run_id — P1 🟢

**Problema**: `configure_logging()` ([config.py](../src/meeting_forge/config.py)) solo emite a
stderr: al cerrar la terminal o reiniciar el contenedor, la evidencia de qué pasó desaparece. El
`run_id` existe en telemetría pero no correlaciona las líneas de log.

**Qué hacer**:
- Sink adicional de loguru a `data/logs/meeting-forge.log` con `rotation="10 MB"`,
  `retention=10`, `serialize=settings.log_json` (JSON opcional para agregadores).
- En `run_pipeline`, envolver el run con `logger.contextualize(run_id=...)` y añadir `{extra}` al
  formato: cada línea del run queda atribuible.

**Aceptación**: tras un run, el fichero contiene las fases con el mismo `run_id`; test del sink con
`tmp_path`.

## PROD-8 · Historial de runs + pestaña Métricas — P1 🟡

**Problema**: la telemetría por run (F2) muere dentro de cada `result.json`. No hay vista agregada:
¿cuánto llevamos gastado este mes? ¿qué reunión fue la más cara/lenta?

**Qué hacer**:
- Al final de `run_pipeline`, apéndice de una línea JSON (`RunTelemetry` + meeting_id) a
  `data/outputs/runs.jsonl` (append-only, robusto ante concurrencia por línea).
- Nueva pestaña **Métricas** en la UI: tabla de runs (fecha, reunión, tokens, coste, latencia),
  totales y coste acumulado del mes. Solo lectura, sin dependencias nuevas (`st.dataframe`).

**Aceptación**: 2 runs → 2 líneas en el jsonl; la pestaña agrega bien un fixture con varios runs.

## PROD-9 · Checkpointing: no repetir trabajo caro — P1 🔴

**Problema**: reprocesar una reunión repite **todo**: transcripción (minutos de CPU) y extracción
(coste LLM), aunque solo quieras regenerar documentos. El transcript ya se persiste
(`<id>_transcript.json`) pero nunca se reutiliza.

**Qué hacer**:
- Guardar `audio_sha256` dentro del transcript JSON. En `run_pipeline`, si existe transcript con
  hash coincidente → saltar transcripción (log claro); `--force-transcribe` / checkbox UI para
  invalidar.
- Comando/acción "regenerar documentos": nueva función en
  [pipeline.py](../src/meeting_forge/pipeline.py) que carga `result.json` existente (insights ya
  extraídos) y ejecuta solo la fase de generación + botón en la UI. Invalida la validación previa
  (mecanismo B-N2 ya existente).

**Aceptación**: segundo run del mismo audio no llama al transcriber (test con transcriber-espía);
"regenerar documentos" no llama al extractor.

## PROD-10 · Docker apto para producción — P1 🟡

**Problema**: la imagen corre como **root**, no tiene `HEALTHCHECK`, y no hay `docker-compose` que
monte volúmenes: los datos y modelos viven dentro del contenedor y se pierden al recrearlo.

**Qué hacer** (sobre el [Dockerfile](../Dockerfile) actual):
- `USER app` no privilegiado; `HEALTHCHECK CMD curl -f http://localhost:8501/_stcore/health`.
- `docker-compose.yml` con volúmenes `./data:/app/data` y `hf-cache:/home/app/.cache`, `env_file`,
  `restart: unless-stopped` y límites de memoria.
- Documentar en README la elección de `WHISPER_MODEL_SIZE` en CPU (medium es lento sin GPU;
  small/base para contenedores modestos).

**Aceptación**: `docker compose up` → UI sana, healthcheck en verde, datos sobreviven a
`down && up`, `whoami` ≠ root.

## PROD-11 · CI endurecido y cadena de suministro — P1 🟡

**Problema**: el [CI](../.github/workflows/ci.yml) no comprueba formato (el pre-commit sí lo hace →
sorpresas entre máquinas), no mide cobertura (pytest-cov instalado pero sin usar), no construye la
imagen Docker y no audita dependencias.

**Qué hacer**:
- Job lint: añadir `ruff format --check .` (y una pasada única de `ruff format .` previa para dejar
  el repo consistente — hoy hay ~14 ficheros heredados sin formatear).
- Tests con `--cov=src --cov-report=xml --cov-fail-under=<actual-5>` (medir primero; subir el
  listón gradualmente, no inventarlo).
- Job `docker build` (sin push) para detectar Dockerfiles rotos.
- `.github/dependabot.yml` (ecosistemas `pip` + `github-actions`, semanal) y job de auditoría de
  vulnerabilidades (`uv export --no-dev | pip-audit -r -`), no bloqueante al principio.
- Alinear la versión de ruff del pre-commit (v0.6.0, antigua) con la del lockfile.

**Aceptación**: CI verde con los jobs nuevos; PR de dependabot de prueba abierto.

## PROD-12 · Tests de UI y E2E — P1 🟡

**Problema**: la UI ([ui/app.py](../src/meeting_forge/ui/app.py), ~600 líneas, con lógica de
aprobación/publicación) tiene **cero tests**: cualquier regresión se descubre a mano. El marker
`integration` existe pero no hay un E2E del pipeline completo con LLM fake.

**Qué hacer**:
- Smoke tests con `streamlit.testing.v1.AppTest`: arrancar la app contra un `data/outputs` temporal
  poblado con `build_demo_meeting()` ([demo.py](../src/meeting_forge/demo.py)); asertar que las 6
  pestañas renderizan sin excepción y que aprobar un documento persiste `validation.json`.
- Test E2E (unit, sin red): `run_pipeline` con transcriber fake + provider fake →
  `result.json` completo + documentos en disco (hoy solo se testea el camino de error de BUG-2).

**Aceptación**: regresiones tipo "claves de widget" (bug 4 de julio) quedarían atrapadas por test.

## PROD-13 · `check --strict` para probes y arranque — P1 🟢

**Problema**: `meeting-forge check` ([cli.py](../src/meeting_forge/cli.py)) informa pero **siempre
sale con código 0**: no sirve como gate de despliegue ni como readiness probe.

**Qué hacer**: flag `--strict` que devuelve exit ≠ 0 si falta un prerequisito de las features
**activadas** (API key del proveedor activo; ffmpeg; índice RAG no vacío si `RAG_ENABLED`; `gh`
autenticado si `GIT_INTEGRATION_ENABLED`). Documentar su uso como healthcheck del CLI y paso previo
en despliegues.

**Aceptación**: matriz de tests con settings monkeypatcheados (falta clave → exit 1; todo OK → 0).

---

# Hito 3 — Producto redondo (P2)

## PROD-14 · Gestión de reuniones desde la UI — P2 🟡

Hoy una reunión procesada es eterna e inmutable: no se puede **borrar, archivar ni corregir el
título/fecha** desde la UI (y la fecha manda en el nombre del acta y la rama Git). Añadir al
sidebar: eliminar reunión (con confirmación, reutilizando el purge de PROD-5) y editar
título/fecha (reescribe `meeting_metadata` en `result.json` e invalida documentos si cambian).

## PROD-15 · Nombres de speaker reales — P2 🟡

La diarización (M7) produce `SPEAKER_00/01`: correcto pero inservible en un acta profesional.
Añadir en la pestaña Transcript un mapeo editable speaker→nombre persistido en `result.json`;
actas y prompts de extracción usan los nombres (mejora además la asignación de `owners`/`assignee`
por el LLM).

## PROD-16 · RAG que aprende de reuniones pasadas — P2 🟡

El corpus RAG es estático (documentación). Las actas/ADRs **ya publicados** son la mejor evidencia
para reuniones futuras ("esto ya se decidió en la reunión del 12-05"). Tras publicar (o aprobar),
indexar los documentos generados en Chroma con `source_path` = ruta en el repo destino
(`delete_by_source` ya evita duplicados al reindexar). Flag `RAG_INDEX_GENERATED_DOCS` (default
true) y exclusión opcional por tipo.

## PROD-17 · Generación de ADRs en paralelo — P2 🟡

`generate_per_decision` ([adr_strategy.py](../src/meeting_forge/generation/adr_strategy.py)) llama
al LLM **secuencialmente**: 6 decisiones ≈ 6× latencia. `ThreadPoolExecutor(max_workers=3)`
preservando el orden de salida; requiere hacer thread-safe el `TelemetryCollector` (lock alrededor
de `_calls.append`) y la caché `_raw_cache`.

## PROD-18 · Notificación al terminar — P2 🟢

En reuniones largas nadie se queda mirando el spinner. Setting `WEBHOOK_URL`: POST JSON (best
effort, nunca rompe el pipeline) al completar un run o crear un PR, compatible con Slack/Teams/
genérico. Un solo módulo `notifications.py` + tests con servidor fake.

## PROD-19 · Backup y restauración documentados — P2 🟢

Definir (README/runbook) qué respaldar: `data/outputs/` (fuente de verdad), `data/raw/` (según
retención), y que ChromaDB es **derivado** — se regenera con `meeting-forge index --clear --sync`.
Añadir `meeting-forge index --rebuild` como alias explícito de ese flujo.

## PROD-20 · Guía de despliegue / runbook — P2 🟡

README cubre desarrollo, no operación. Documento `docs/DEPLOYMENT.md`: requisitos de máquina
(CPU/RAM/disco según modelo Whisper), compose de referencia (PROD-10), reverse proxy + TLS
(PROD-1), variables obligatorias por feature, troubleshooting de los fallos típicos (sin ffmpeg,
índice vacío, `gh` sin auth, coste/presupuesto) y procedimiento de actualización de versión.

---

# Futuro (P3)

- **PROD-21 · API HTTP (FastAPI)** 🔴: endpoints `POST /meetings` (audio) + `GET /meetings/<id>` para
  integraciones (bots de Slack/Teams que suban la grabación automáticamente). Reutiliza
  `pipeline.py` tal cual; requiere resolver ejecución en background (cola) — hacer después de
  PROD-3.
- **PROD-22 · Multi-usuario real** 🔴: identidad por usuario (quién aprobó qué ya se persiste en
  `validation.json`, pero sin identidad), roles (validador vs administrador).
- **PROD-23 · Export PDF/DOCX de actas** 🟡: vía pandoc opcional (dependencia externa documentada),
  para organizaciones donde el entregable no es Markdown.

## Fuera de alcance (decisión explícita)

- Transcripción en streaming / tiempo real (otro producto).
- Multi-tenancy SaaS, facturación.
- i18n de la UI (el producto es en español por diseño del TFM).

## Orden recomendado de ejecución

1. **PROD-6** y **PROD-13** (🟢, una tarde): licencia, versión, check estricto.
2. **PROD-2 → PROD-3 → PROD-4**: robustez de ejecución (lo que más riesgo real quita).
3. **PROD-1 + PROD-5**: seguridad y datos → con esto se puede **desplegar a un equipo piloto**.
4. **PROD-10 + PROD-11 + PROD-7**: despliegue y CI serios.
5. **PROD-8, PROD-9, PROD-12** y luego el Hito 3 según feedback del piloto.
