# Plan 04 · Mejoras para el usuario

> Parte de [`planes/`](00-orquestador.md). Mejoras **de cara al usuario final**: que los resultados
> sean mejores y más fiables, y que la app haga más cosas útiles. Lo operacional (auth, Docker,
> CI, timeouts…) vive en [`03-produccion.md`](03-produccion.md); aquí solo producto y UX.
> Absorbe los ítems de producto que estaban en el plan 03 (PROD-14/15/16/23) para tenerlos juntos.

## Cómo leer este documento

- **Prioridad**: `P0` (máximo valor para el usuario) → `P3` (deseable).
- **Esfuerzo**: 🟢 < 2 h · 🟡 medio día–1 día · 🔴 varios días.
- Prefijo **UX-n**. Cada ítem independiente: una rama/PR con su test cuando aplique.
- Guía de priorización: primero lo que mejora la **calidad del resultado** (es el corazón del
  producto: si el acta sale mala, lo demás da igual), luego lo que convierte la app en
  **herramienta de equipo continua**, luego el pulido.

## Estado de implementación

> Actualizado: **2026-07-05**. Cambios en el árbol de trabajo (aún **sin commitear**).
> Gates tras los cambios: `ruff check` ✅ · `mypy src --strict` ✅ (51 ficheros) · `pytest` ✅ **316 passed**.

**✅ Completados — Paso 1 del orden recomendado (quick wins de calidad)**

- **UX-1** — `build_initial_prompt()` combina `WHISPER_INITIAL_PROMPT` + `data/glossary.txt` +
  vocabulario por-run (campo en la UI y `--vocabulary` en el CLI), con truncado defensivo
  ([transcriber.py](../src/meeting_forge/ingestion/transcriber.py), [config.py](../src/meeting_forge/config.py),
  [.env.example](../.env.example)). Tests: [test_transcriber.py](../tests/unit/test_transcriber.py).
- **UX-4** — asistentes de la reunión: `parse_attendees()` + `--attendees` en el CLI + campo en la UI;
  llegan a `MeetingMetadata.attendees` y al acta ([pipeline.py](../src/meeting_forge/pipeline.py),
  [cli.py](../src/meeting_forge/cli.py), [ui/app.py](../src/meeting_forge/ui/app.py)).
  Tests: [test_pipeline.py](../tests/unit/test_pipeline.py).
- **UX-12** — grabación desde el micrófono (`st.audio_input`) con nombre único por timestamp
  (sin él, cada grabación pisaría la anterior) ([ui/app.py](../src/meeting_forge/ui/app.py)).
- **UX-13** — el uploader acepta vídeo (mp4/webm/mkv/mov/avi) y los contenedores de vídeo fuerzan
  la extracción de audio con ffmpeg aunque el preprocesado esté off; passthrough tolerante si no hay
  ffmpeg ([preprocessor.py](../src/meeting_forge/ingestion/preprocessor.py),
  [transcriber.py](../src/meeting_forge/ingestion/transcriber.py)).
  Tests: [test_preprocessor.py](../tests/unit/test_preprocessor.py), [test_transcriber.py](../tests/unit/test_transcriber.py).
- **UX-18** — nuevo módulo compartido [system_status.py](../src/meeting_forge/system_status.py)
  (checks de API key del proveedor activo, ffmpeg, gh, índice RAG con `count` inyectable); expander
  "⚙️ Estado del sistema" en el sidebar con ✅/⚠️ + remedio, botón «Procesar» deshabilitado si falta
  la clave LLM, y `meeting-forge check` refactorizado para usar los mismos checks.
  Tests: [test_system_status.py](../tests/unit/test_system_status.py).

**✅ Completados — Paso 2 del orden recomendado (ciclo HITL completo)**

> Gates tras el paso 2: `ruff check` ✅ · `mypy src --strict` ✅ (53 ficheros) · `pytest` ✅ **342 passed**.

- **Base (PROD-9 parcial)** — regeneración parcial del pipeline: `regenerate_documents()` (solo
  generación, desde insights persistidos) y `rerun_extraction()` (extracción + generación desde el
  transcript persistido, sin re-transcribir), ambas con limpieza de documentos huérfanos
  (`_clear_generated_dirs`), invalidación de la validación (B-N2) y result.json atómico
  ([pipeline.py](../src/meeting_forge/pipeline.py)). El bloque de generación de `run_pipeline` quedó
  refactorizado en helpers compartidos (`_generate_docs`/`_write_docs`) y ahora también limpia
  huérfanos al reprocesar. Nuevo módulo [meeting_store.py](../src/meeting_forge/meeting_store.py)
  (lectura/escritura del estado por reunión). Tests: [test_pipeline.py](../tests/unit/test_pipeline.py),
  [test_meeting_store.py](../tests/unit/test_meeting_store.py).
- **UX-3** — nombres de hablantes: `Transcript.rename_speakers()` + `to_text()` con prefijo
  `Hablante: …` ([ingestion/schemas.py](../src/meeting_forge/ingestion/schemas.py)); formulario
  "🗣️ Nombres de hablantes" en la pestaña Transcript, persistido como `speaker_names` en
  result.json y aplicado en la re-extracción (el LLM ve nombres reales).
  Tests: [test_schemas.py](../tests/unit/test_schemas.py).
- **UX-2** — transcript corregible: la pestaña Transcript es ahora un `st.data_editor`
  (texto/speaker editables, tiempos bloqueados; vaciar el texto elimina el segmento), con
  «💾 Guardar transcript» (actualiza fichero canónico + result.json) y «🔁 Re-extraer insights»
  ([ui/app.py](../src/meeting_forge/ui/app.py)).
- **UX-5** — insights editables: toggle "✏️ Editar insights" con resumen, temas, decisiones y
  tareas en `st.data_editor` (filas añadibles/borrables); las **fuentes se preservan** vía la
  columna `#` (helpers puros en
  [analysis/insights_editing.py](../src/meeting_forge/analysis/insights_editing.py));
  «Guardar y regenerar documentos» marca `insights_edited` y regenera todo.
  Tests: [test_insights_editing.py](../tests/unit/test_insights_editing.py).

**✅ Completados — Paso 3 del orden recomendado (valor de equipo)**

> Gates tras el paso 3: `ruff check` ✅ · `mypy src --strict` ✅ (57 ficheros) · `pytest` ✅ **372 passed**.

- **UX-7** — panel global de tareas: nuevo módulo [tasks.py](../src/meeting_forge/tasks.py) (agrega
  `action_items` de todas las reuniones, estado hecha/pendiente en `data/outputs/tasks.json` con
  clave estable `meeting_id`+hash, filtro por asignado y export CSV); vista "Tareas" en la UI.
  Tests: [test_tasks.py](../tests/unit/test_tasks.py).
- **UX-10** — pantalla de inicio: nuevo módulo [dashboard.py](../src/meeting_forge/dashboard.py)
  (reuniones, docs por validar, tareas abiertas/totales, recientes); vista "Inicio" con tarjetas y
  accesos directos. Tests: [test_dashboard.py](../tests/unit/test_dashboard.py).
- **UX-8** — búsqueda entre reuniones: nuevo módulo [search.py](../src/meeting_forge/search.py)
  (colección Chroma separada `meeting_forge_meetings`, un chunk por reunión, indexación best-effort
  al procesar/re-extraer, fallback por subcadena), caja "🔎 Buscar" en el sidebar y comando
  `meeting-forge search <query> [--reindex]`. Tests: [test_search.py](../tests/unit/test_search.py).
- **UX-9** — memoria RAG: nuevo módulo [memory.py](../src/meeting_forge/memory.py) (indexa el
  contenido efectivo de los documentos aprobados en el corpus RAG con `source_path` estable
  `meetings/<id>/<kind>/<file>`); hook best-effort tras publicar en
  [publisher.py](../src/meeting_forge/git_integration/publisher.py). Flags `SEARCH_INDEX_ENABLED` /
  `RAG_INDEX_GENERATED_DOCS`. Tests: [test_memory.py](../tests/unit/test_memory.py).

Además: la UI pasa a tener navegación (Inicio / Reunión / Tareas) en el sidebar.

**✅ Completados — Paso 4 del orden recomendado (los 🔴 estrella para la demo)**

> Gates tras el paso 4: `ruff check` ✅ · `mypy src --strict` ✅ (58 ficheros) · `pytest` ✅ **386 passed**.

- **UX-6** — citas al minuto de audio: `Transcript.to_indexed_text()` emite el transcript con
  marcadores `[S<n>]`; el extractor resuelve los marcadores `S<n>` del LLM a `TranscriptRef`
  (índice + tiempos + texto) igual que los `#N` de RAG, con schema nuevo `TranscriptRef` en
  [analysis/schemas.py](../src/meeting_forge/analysis/schemas.py) y campo `transcript_refs` en
  `Decision`/`ActionItem`. Prompts v1/v2 actualizados. La pestaña Insights muestra los momentos
  `mm:ss` y un `st.audio(start_time=…)` que arranca en el instante citado. Tests:
  [test_extractor_sources.py](../tests/unit/test_extractor_sources.py),
  [test_schemas.py](../tests/unit/test_schemas.py).
- **UX-11** — chat con la reunión: nuevo módulo [chat.py](../src/meeting_forge/chat.py) (selección
  de segmentos relevantes por solape de tokens, prompt con insights + segmentos indexados +
  historial, parseo de `[S<n>]` citados); pestaña "Preguntar" con `st.chat_input`, historial en
  sesión, reproductor en los momentos citados y contador de coste por sesión.
  Tests: [test_chat.py](../tests/unit/test_chat.py).
- La demo ([demo.py](../src/meeting_forge/demo.py)) incluye `transcript_refs` para mostrar UX-6.

Con esto quedan implementados los 4 pasos del orden recomendado. Pendientes (no bloqueantes):
UX-9 bonus ("decisiones relacionadas"), y el Tema 4 de pulido (UX-14/15/16/17/19/20) según feedback.

---

## El recorrido del usuario hoy (y sus fricciones)

```
Sube audio → espera (sin % de progreso) → lee transcript (con errores en términos técnicos,
speakers anónimos) → lee insights (no puede corregirlos) → valida documentos (sí puede editarlos)
→ publica. Cada reunión es una isla: no hay búsqueda, ni tareas agregadas, ni memoria entre
reuniones. Los asistentes nunca aparecen en el acta (el campo existe y siempre va vacío).
```

---

## Resumen (tabla)

| # | Mejora | Prioridad | Esfuerzo | Tema |
|---|---|---|---|---|
| UX-1 | Glosario del proyecto para Whisper | **P0** | 🟢 | Calidad |
| UX-2 | Corregir el transcript y re-extraer | **P0** | 🟡 | Calidad |
| UX-3 | Nombres reales de speakers | **P0** | 🟡 | Calidad |
| UX-4 | Asistentes de la reunión en el acta | **P0** | 🟢 | Calidad |
| UX-5 | Editar insights antes de generar docs | **P0** | 🔴 | Calidad |
| UX-6 | Citas al minuto de audio + reproductor | P1 | 🔴 | Calidad |
| UX-7 | Panel global de tareas pendientes | P1 | 🟡 | Equipo |
| UX-8 | Búsqueda entre reuniones | P1 | 🟡 | Equipo |
| UX-9 | Memoria de decisiones pasadas (RAG) | P1 | 🟡 | Equipo |
| UX-10 | Pantalla de inicio (dashboard) | P1 | 🟡 | Equipo |
| UX-11 | Chat con la reunión (Q&A) | P1 | 🔴 | Interacción |
| UX-12 | Grabar desde el micrófono | P2 | 🟢 | Interacción |
| UX-13 | Aceptar vídeo y más formatos | P2 | 🟢 | Interacción |
| UX-14 | Progreso real durante la transcripción | P2 | 🟡 | Pulido |
| UX-15 | Gestionar reuniones: renombrar/borrar | P2 | 🟡 | Pulido |
| UX-16 | Descargas mejores: ZIP, PDF/DOCX | P2 | 🟡 | Pulido |
| UX-17 | Elegir modelo/proveedor por reunión | P2 | 🟢 | Pulido |
| UX-18 | Panel "estado del sistema" en la UI | P2 | 🟢 | Pulido |
| UX-19 | Procesado por lotes (CLI) | P3 | 🟢 | Interacción |
| UX-20 | Plantillas de acta/ADR personalizables | P3 | 🟡 | Pulido |

---

# Tema 1 · Resultados de más calidad (P0)

> La cadena es: transcript → insights → documentos. Un error al principio contamina todo lo
> demás. Estas mejoras atacan la calidad en origen y dan al usuario control en cada eslabón.

## UX-1 · Glosario del proyecto para Whisper — P0 🟢

**Fricción**: Whisper destroza los términos técnicos y nombres propios del proyecto ("ChromaDB" →
"croma de ve", "Nacho" → "nacho"). Es el error más visible del producto y contamina extracción y
documentos.

**Qué hacer**: faster-whisper soporta `initial_prompt`: un texto que condiciona el vocabulario.
- Setting `WHISPER_INITIAL_PROMPT` y/o fichero `data/glossary.txt` (una línea por término) que
  [transcriber.py](../src/meeting_forge/ingestion/transcriber.py) concatena y pasa a
  `model.transcribe(..., initial_prompt=...)`.
- Campo opcional "Vocabulario/contexto" en el formulario de subida de la UI (persiste como default).

**Valor**: mejora inmediata y barata del eslabón que más se nota. **Aceptación**: test de que el
prompt llega al modelo (transcriber con model fake); glosario vacío = comportamiento actual.

## UX-2 · Corregir el transcript y re-extraer — P0 🟡

**Fricción**: el transcript es de solo lectura. Si Whisper entendió mal una frase clave, el error
llega hasta el acta y el usuario no puede hacer nada salvo editar el documento final a mano (y
perder la coherencia con insights/citas).

**Qué hacer**:
- En la pestaña Transcript, `st.data_editor` sobre los segmentos (columna Texto editable, Speaker
  editable). "Guardar transcript" reescribe `<id>_transcript.json` y el bloque `transcript` de
  `result.json`.
- Botón "Re-extraer insights" que ejecuta solo extracción + generación sobre el transcript
  corregido (necesita la función de re-generación parcial; ver PROD-9 en
  [03-produccion.md](03-produccion.md), son complementarios). Invalida la validación previa
  (mecanismo B-N2 ya existente).

**Valor**: cierra el ciclo HITL también en el primer eslabón, no solo en el último.
**Aceptación**: editar un segmento y re-extraer produce insights basados en el texto corregido
(test con provider fake que devuelve lo que recibe).

## UX-3 · Nombres reales de speakers — P0 🟡

**Fricción**: la diarización (M7) etiqueta `SPEAKER_00/01`: correcto técnicamente, inservible en
un acta profesional ("SPEAKER_01 se compromete a…").

**Qué hacer**:
- En la pestaña Transcript, si hay speakers: mapeo editable `SPEAKER_00 → Nacho` (uno por speaker
  detectado), persistido en `result.json` (`speaker_names`) y aplicado en la vista, el acta y el
  texto que ve el LLM.
- `Transcript.to_text()` ([ingestion/schemas.py](../src/meeting_forge/ingestion/schemas.py)) gana
  variante con prefijo de hablante (`Nacho: hola…`) cuando hay speakers: el extractor asigna
  `owners`/`assignee` muchísimo mejor con nombres delante.

**Valor**: actas con personas, no etiquetas; mejores responsables en decisiones y tareas.
**Aceptación**: renombrar y regenerar el acta muestra nombres; extracción recibe el texto prefijado.

## UX-4 · Asistentes de la reunión en el acta — P0 🟢

**Fricción**: `MeetingMetadata.attendees` existe ([generation/schemas.py](../src/meeting_forge/generation/schemas.py))
y la plantilla del acta ya lo renderiza… pero **nadie lo rellena nunca**: ni la UI ni el CLI lo
piden. Todas las actas salen sin asistentes.

**Qué hacer**: campo "Asistentes" (texto separado por comas) en el formulario de subida de la UI y
opción `--attendees` en el CLI `run`; con UX-3 hecho, ofrecer los nombres de speakers como
sugerencia. Editable a posteriori (junto con título/fecha, UX-15).

**Aceptación**: el acta generada lista los asistentes introducidos.

## UX-5 · Editar insights antes de generar documentos — P0 🔴

**Fricción**: la pestaña Insights es un visor. Si el LLM extrajo una decisión mal (o se inventó
una, o se dejó una tarea), el usuario solo puede editar el **Markdown final** — arreglando el
síntoma documento a documento, mientras `result.json`, el acta y los ADRs siguen guardando el dato
malo.

**Qué hacer**:
- Modo edición en la pestaña Insights: editar título/descripción/responsables de cada decisión,
  añadir/eliminar decisiones y tareas (`st.data_editor` para tareas; formulario por decisión).
- "Guardar y regenerar documentos": persiste los insights corregidos en `result.json` (marcando
  `insights_edited: true` para auditoría) y regenera los documentos desde ellos, invalidando la
  validación previa. Reutiliza la regeneración parcial de UX-2/PROD-9.

**Valor**: es el HITL que de verdad importa — corregir la *fuente* y que todos los documentos
salgan bien, en vez de parchear salidas. **Aceptación**: editar una decisión y regenerar produce
ADR y acta con el contenido corregido; las citas [^N] de fuentes sobreviven a la edición.

## UX-6 · Citas al minuto de audio + reproductor — P1 🔴

**Fricción**: cada decisión cita documentación (SourceRef), pero no **dónde se dijo en la
reunión**. Para verificar "¿de verdad decidimos esto?", el usuario tiene que rebuscar en el
transcript a ojo.

**Qué hacer**:
- El transcript que ve el LLM lleva índices de segmento (`[S12]`); el schema crudo de extracción
  ([extractor.py](../src/meeting_forge/analysis/extractor.py)) gana `transcript_refs: list[str]`
  por decisión/tarea, resuelto a rangos de segmentos con sus timestamps (mismo patrón que los
  marcadores `#N` de RAG — infraestructura ya probada).
- En Insights/Evidencia: junto a cada decisión, las frases citadas del transcript con su
  `mm:ss`, y `st.audio(data/raw/<audio>, start_time=<s>)` para **escuchar el momento exacto**
  (si el audio se conserva; ver retención en el plan 03).

**Valor**: confianza total en la extracción; demo espectacular para el tribunal. **Aceptación**:
decisión extraída de un transcript sintético cita los segmentos correctos; el reproductor arranca
en el timestamp.

---

# Tema 2 · De archivo de reuniones a herramienta de equipo (P1)

> Hoy cada reunión es una isla. El valor compuesto está en el corpus de reuniones.

## UX-7 · Panel global de tareas pendientes — P1 🟡

**Fricción**: las tareas extraídas (`action_items` con asignado y deadline) se quedan enterradas
dentro de cada reunión. Nadie va a abrir 15 reuniones para saber qué tiene pendiente.

**Qué hacer**:
- Vista "Tareas" (global, no por reunión): agrega los `action_items` de todos los `result.json`
  ([ui/loader.py](../src/meeting_forge/ui/loader.py) ya sabe listar reuniones), con columnas
  asignado / deadline / reunión de origen (enlace) / estado.
- Estado "hecha/pendiente" persistido en `data/outputs/tasks.json` (clave estable:
  meeting_id + hash de la descripción). Filtros por asignado y export CSV
  (`st.download_button`).

**Valor**: convierte la app en algo que se abre cada día, no solo tras cada reunión.
**Aceptación**: tareas de 2 reuniones fixture aparecen agregadas; marcar hecha sobrevive al rerun.

## UX-8 · Búsqueda entre reuniones — P1 🟡

**Fricción**: "¿en qué reunión hablamos de la migración?" no tiene respuesta hoy: no hay búsqueda.

**Qué hacer**:
- Al terminar cada run, indexar transcript + insights en una **colección Chroma separada**
  (`meeting_forge_meetings` — [ChromaVectorStore](../src/meeting_forge/rag/vector_store.py) ya
  acepta `collection_name`), con metadata `meeting_id`.
- Caja de búsqueda en el sidebar: semántica (embeddings ya cargados) con fallback a substring
  sobre los `result.json`. Resultados → enlace que selecciona la reunión y pestaña.

**Valor**: el corpus de reuniones se vuelve consultable. **Aceptación**: buscar un término de la
reunión B estando en la A la encuentra y navega a ella.

## UX-9 · Memoria de decisiones pasadas en el RAG — P1 🟡

**Fricción**: el RAG solo ve documentación estática. Las decisiones ya tomadas — la mejor
evidencia para una reunión nueva ("esto ya se decidió el 12-05") — no participan. *(Era PROD-16.)*

**Qué hacer**:
- Tras aprobar/publicar, indexar las actas y ADRs generados en el corpus RAG con
  `source_path` estable (`delete_by_source` ya evita duplicados al re-aprobar). Flag
  `RAG_INDEX_GENERATED_DOCS` (default true).
- Bonus en la UI: en cada decisión nueva, expander "Decisiones relacionadas" con las 3 más
  similares del pasado (query a Chroma con el título+descripción).

**Valor**: el sistema mejora con el uso; detecta contradicciones con acuerdos previos.
**Aceptación**: una decisión de la reunión 2 similar a una de la reunión 1 muestra la relación.

## UX-10 · Pantalla de inicio (dashboard) — P1 🟡

**Fricción**: la app aterriza directamente en una reunión concreta. No hay visión de conjunto:
qué hay pendiente de validar, qué se procesó esta semana, cuántas tareas abiertas.

**Qué hacer**: vista inicial cuando no hay reunión seleccionada (o entrada "Inicio" en el
sidebar): tarjetas con nº de reuniones, documentos pendientes de validar (leyendo los
`validation.json`), tareas abiertas (UX-7) y las 5 reuniones recientes con acceso directo. Botón
"Crear reunión de ejemplo" (reutiliza [demo.py](../src/meeting_forge/demo.py)) cuando esté vacío.

**Aceptación**: con outputs fixture, el dashboard cuenta bien pendientes y recientes.

---

# Tema 3 · Interacción más rica

## UX-11 · Chat con la reunión (Q&A) — P1 🔴

**Fricción**: leer un transcript de 90 minutos para responder "¿qué dijo Marta del presupuesto?"
no es razonable. El resumen es estático y no responde preguntas.

**Qué hacer**: pestaña "Preguntar" por reunión: `st.chat_input` + historial en session_state.
Contexto = insights + chunks relevantes del transcript (troceado con
[`_sliding_windows`](../src/meeting_forge/rag/retriever.py) + embeddings en memoria; sin tocar el
índice persistente). Respuestas con `provider.complete()` citando los `mm:ss` de los segmentos
usados. Contador de coste visible (telemetría ya existente).

**Valor**: la feature más "IA-nativa" del producto; demo potente. **Aceptación**: pregunta sobre
un transcript fixture responde citando el segmento correcto (provider fake).

## UX-12 · Grabar desde el micrófono — P2 🟢

**Fricción**: para una nota de voz o una reunión improvisada hay que grabar con otra app y subir
el fichero.

**Qué hacer**: `st.audio_input` (Streamlit ≥ 1.40, ya en
[pyproject.toml](../pyproject.toml)) como alternativa al file_uploader en el panel "Procesar
nueva reunión"; el WAV resultante entra por el mismo `_process_uploaded`.

**Aceptación**: grabar 10 s desde el navegador dispara el pipeline normal.

## UX-13 · Aceptar vídeo y más formatos — P2 🟢

**Fricción**: las reuniones reales son grabaciones de Meet/Teams/Zoom (`.mp4`, `.webm`, `.mkv`);
hoy el uploader solo acepta `wav/mp3/m4a/flac/ogg` y obliga a convertir fuera.

**Qué hacer**: ampliar `type=[...]` en [ui/app.py](../src/meeting_forge/ui/app.py) con
`mp4, webm, mkv, aac, wma`; para contenedores de vídeo, forzar el paso por
[preprocessor.py](../src/meeting_forge/ingestion/preprocessor.py) (ffmpeg extrae la pista de
audio a WAV 16 kHz — el flujo F9 ya existe, solo hay que activarlo por extensión).

**Aceptación**: un `.mp4` de prueba se transcribe igual que un `.wav`.

## UX-19 · Procesado por lotes (CLI) — P3 🟢

Para digerir un backlog de grabaciones: `meeting-forge run-batch <dir>` que procesa cada audio no
procesado aún (skip si ya existe `outputs/<stem>/`), con resumen final. Solo CLI, sin UI.

---

# Tema 4 · Pulido de experiencia

## UX-14 · Progreso real durante la transcripción — P2 🟡

**Fricción**: "Transcribiendo audio con Whisper…" puede durar 10 minutos sin señal de vida; el
usuario no sabe si avanza o se colgó.

**Qué hacer**: `segments_raw` de faster-whisper es un **generador**: consumirlo reportando
`seg.end / info.duration` a un callback opcional de
[transcriber.transcribe()](../src/meeting_forge/ingestion/transcriber.py), conectado al
`ProgressCallback` del pipeline → `st.progress` con porcentaje y tiempo transcrito ("12:30 /
45:00"). El CLI loguea cada 10 %.

**Aceptación**: transcriber fake que emite 3 segmentos produce 3 actualizaciones de progreso.

## UX-15 · Gestionar reuniones: renombrar, borrar, reordenar — P2 🟡

*(Era PROD-14.)* Editar título/fecha/asistentes tras el procesado (reescribe `meeting_metadata` en
`result.json`; avisa de que la fecha afecta al nombre de acta y rama Git), borrar reunión con
confirmación, y ordenar el selector por fecha de reunión además de por procesado.

## UX-16 · Descargas mejores: ZIP, PDF/DOCX — P2 🟡

*(Absorbe PROD-23.)* Botón "Descargar todo (ZIP)" por reunión (`zipfile` + `io.BytesIO`, sin
dependencias). Export a PDF/DOCX vía pandoc **si está instalado** (patrón tolerante a ausencia,
como ffmpeg/gh): el botón aparece solo si `shutil.which("pandoc")`.

## UX-17 · Elegir modelo/proveedor por reunión — P2 🟢

**Fricción**: el proveedor/modelo es global (`.env`). Un standup no necesita el mismo modelo que
un consejo de arquitectura, y cambiar `.env` + reiniciar no es razonable.

**Qué hacer**: selectbox opcional en el panel de subida (default: settings) → parámetro
`provider_name` en `run_pipeline` → `get_provider(name=...)`
([llm_client.py](../src/meeting_forge/analysis/llm_client.py) ya tiene el factory). El proveedor
usado ya se persiste en `metadata` y se muestra en el sidebar.

## UX-18 · Panel "estado del sistema" en la UI — P2 🟢

**Fricción**: cuando algo falta (API key, índice vacío, `gh` sin auth, ffmpeg) el usuario lo
descubre por un error a mitad de proceso. `meeting-forge check` existe pero es CLI.

**Qué hacer**: expander "⚙️ Estado" en el sidebar reutilizando las mismas comprobaciones del
`check` (las funciones ya están importadas en [ui/app.py](../src/meeting_forge/ui/app.py)):
✅/⚠️ por prerequisito con el remedio en una línea. Deshabilitar "Procesar" si falta lo esencial,
con motivo visible.

## UX-20 · Plantillas personalizables — P3 🟡

El sistema de prompts versionados (`prompts/generation/adr_v1.md`…) ya permite variantes: exponer
`ADR_PROMPT_VERSION` y las plantillas de acta como algo que el usuario puede duplicar y ajustar
(cabecera corporativa, secciones extra), con selector de versión en la UI y doc de cómo crear una
versión nueva.

---

## Orden recomendado

1. **Quick wins de calidad** (1–2 días en total): **UX-1** (glosario), **UX-4** (asistentes),
   **UX-18** (estado del sistema), **UX-12/13** (micro + vídeo). Mejora visible inmediata.
2. **El ciclo HITL completo**: **UX-3** (speakers) → **UX-2** (corregir transcript) → **UX-5**
   (editar insights). Es la inversión más rentable: controla la calidad en cada eslabón.
3. **Valor de equipo**: **UX-7** (tareas) + **UX-10** (dashboard), luego **UX-8/9** (búsqueda y
   memoria).
4. **Los 🔴 estrella para la demo**: **UX-6** (citas al minuto + audio) y **UX-11** (chat), cuando
   lo anterior esté asentado.

## Dependencias con el plan 03

- UX-2 y UX-5 necesitan la **regeneración parcial** (PROD-9) — conviene implementarla primero.
- UX-6 y UX-11 suben el nº de llamadas LLM → el **tope de coste** (PROD-4) gana importancia.
- UX-7/8/9 escriben más estado en disco → el **purge** (PROD-5) debe cubrirlo.
