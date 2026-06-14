# Plan 00 · Orquestador

> Documento índice de la carpeta `planes/`. Resume el análisis de `propuesta_tfm.pdf` y del repositorio,
> y define el **roadmap priorizado** que ata los dos planes de detalle:
> - [`01-bugs-y-deuda-tecnica.md`](01-bugs-y-deuda-tecnica.md) — qué arreglar.
> - [`02-features.md`](02-features.md) — qué construir.

---

## 1. Resumen ejecutivo

**MeetingForge** es el sistema del TFM: transforma **reuniones técnicas en documentación estructurada y versionada**
mediante IA generativa. La propuesta plantea un pipeline modular y reproducible; el repositorio ya implementa la
mayor parte:

```
Audio → Whisper (faster-whisper)
      → RAG (ChromaDB + sentence-transformers, provenance con SourceRef)
      → Insights con citas (LLM: Anthropic / OpenAI)
      → Generación de ADRs y Actas (citas [^N] reales)
      → UI Streamlit (visor + validación)
      → Human-in-the-loop → Publicación Git + PR (gh)
```

Los 6 módulos del pipeline existen y están testeados. Las **brechas** respecto a la propuesta son, sobre todo:
**evaluación/métricas** (objetivo 7, inexistente), **doc técnica + roadmap** (objetivo 4, parcial) y **ejecutar el
pipeline desde la UI** (objetivo 6, hoy visor read-only).

## 2. Estado actual verificado (2026-05-31)

Comprobado sobre el código real **en su estado actual** (posterior a la "Fase 5: Mejoras"):

| Comprobación | Resultado |
|---|---|
| `ruff check .` | ✅ All checks passed |
| `mypy src` (`--strict`) | ✅ Success, no issues in 38 files |
| `pytest` | ✅ 189 passed, 2 skipped (integración) |
| Test flaky histórico | ✅ Arreglado |
| CI (`ruff`+`mypy`+`pytest`) y pre-commit (`ruff`) | ✅ Presentes |
| README/ARCHITECTURE | ✅ Reflejan Fase 4 |

➡️ **Importante**: el `MEJORAS_PROYECTO.md` de la raíz es **anterior** a estas mejoras; sus P0 (ruff/mypy/flaky/CI)
**ya están hechos**. Estos planes lo **sustituyen** como fuente de verdad y se centran en lo que sigue abierto.

## 3. Cómo se relacionan los dos planes

- Muchas **features** dependen de **arreglos** previos. Ejemplos:
  - **F1 (evaluación)** del RAG no es válida sin **B1/B2** (índice contaminado por `.venv` / chunks obsoletos).
  - **F1/F2** (métricas de coste/latencia) necesitan **B5** (max_tokens real) y la telemetría en el cliente LLM.
  - **F3** formaliza **TD7 + TD8** (persistir metadata y evidencia).
  - **F6** recoge **B1/B2/B7/B8**; **F7** recoge **B9/B10/B11/TD9**.
- Por eso el roadmap **intercala** arreglos y features por fases, priorizando **completitud del TFM**.

## 4. Roadmap priorizado (completitud del TFM primero)

Tres fases, cada una con un **hito demostrable**.

### Fase A — Cerrar la brecha académica (lo que da la memoria) 🎯

Objetivo: que el sistema sea **medible y reproducible**.

> **Progreso (2026-05-31)**: **Fase A completada** ✅ (gates en verde: `ruff`/`mypy` ✅ · `pytest` **215 passed, 2 skipped**).
> Detalle en [`01-bugs-y-deuda-tecnica.md` › Estado de implementación](01-bugs-y-deuda-tecnica.md#estado-de-implementación)
> y [`02-features.md` › Estado de implementación](02-features.md#estado-de-implementación).

1. ✅ **Quick wins**: `B3` (validation.json), `B4` (idioma/duración), `B5` (max_tokens), `TD4` (código muerto),
   `B12` (README), `TD12` (designorar `uv.lock`), matriz CI (`TD11`).
2. ✅ **Índice RAG limpio**: `B1` (excluir `.venv`/ruido) → `B2` (podar chunks obsoletos). *(con tests)*
3. ✅ **Persistir datos**: `F3` (= `TD7` metadata + `TD8` evidencia) en `result.json`; la UI relee la metadata.
4. ✅ **Observabilidad**: `F2` (`run_id`, tiempos por fase, tokens, latencia, coste) → `run_meta` en `result.json`.
5. ✅ **Evaluación**: `F1` (paquete `evaluation/` + `scripts/evaluate.py` + dataset de ejemplo; verificado end-to-end).

**Hito A** ✅: `scripts/evaluate.py` produce **tablas cuantitativas reproducibles** (WER, P/R/F1, precision@k) para
los anexos de la memoria. *Siguiente refinamiento*: alimentar el harness con predicciones del pipeline real y volcar
latencia/coste desde `run_meta`.

### Fase B — Robustez para una defensa fiable 🛡️

Objetivo: que el pipeline aguante uso real y revisión técnica.

> **Progreso (2026-05-31)**: **Fase B completada** ✅ (gates: `ruff`/`mypy` ✅ · `pytest` **227 passed, 2 skipped**).

- ✅ Toda la deuda/bugs de Fase B resuelta: `TD1`, `TD2`, `TD3`, `TD5`, `TD6`, `TD13`, `B6` (+ `B7`–`B11`, `TD9`).
- 🟡 `F6` (RAG): `B7`/`B8` + **sync de borrados** hechos; queda solo **filtros** de retrieval. · 🟡 `F7` (Git):
  `B9`/`B10`/`B11`/`TD9` + **repo sucio** + **fallback de compare** hechos; queda solo **`--dry-run`**.
- 🟡 `TD10` (cobertura muy ampliada; solo falta el test del transcriptor).

**Hito B**: pipeline end-to-end **robusto y seguro**, con cobertura de tests ampliada y `ruff`/`mypy`/`pytest` verdes en CI multi-plataforma.

### Fase C — Ampliar producto y demostrabilidad 🚀

Objetivo: completar la *visión* de la propuesta y facilitar la demo.

> **Progreso (2026-05-31)**: **Fase C completada** ✅ (gates: `ruff`/`mypy` ✅ · `pytest` **262 passed, 2 skipped**).

- ✅ `F4` (ejecutar el pipeline desde la UI): orquestación extraída a un servicio reutilizable
  [`pipeline.py`](../src/meeting_forge/pipeline.py) + panel de subida/ejecución con **progreso por fase** en
  Streamlit. Cierra el **objetivo 6** de la propuesta.
- ✅ `F5` (doc técnica + roadmap + **actualizar docs existentes** con diff): **completo**. Cierra el **objetivo 4**.
- ✅ `F10` (empaquetado + demo): entrypoint `meeting-forge` (`run`/`index`/`eval`/`demo`/`check`) + **demo offline**
  reproducible sin API keys + comando `check` de prerequisitos. Pendiente opcional: Dockerfile.
- ✅ `F11` (UX de validación): "Aprobar" **preserva la edición en curso** + diff de la edición vs el original.
- ✅ `F12` (proveedores LLM): **validación de API keys** al iniciar + **retries con backoff**. Ollama ya estaba.
  Pendiente opcional: structured outputs estrictos.
- ✅ `F8` (modo automático opcional): auto-aprueba **solo la allowlist** (default actas) con auditoría/badge +
  auto-publicación opcional con **PRs borrador**. Desactivado por defecto.
- ✅ `F9` (robustez de audio): preprocesado opcional con **ffmpeg** (mono + 16 kHz + `loudnorm`), tolerante a
  fallos (passthrough). Pendiente opcional: diarización real (pyannote).

**Flecos opcionales restantes** (no bloquean nada): Dockerfile (F10), structured outputs estrictos (F12),
filtros de retrieval (F6), `--dry-run` (F7), diarización (F9).

**Hito C** ✅: **demo reproducible** (`meeting-forge demo` → UI) + flujo end-to-end (subir audio → revisar →
publicar PR) listos para el tribunal.

## 5. Trazabilidad propuesta ↔ estado

| # | Objetivo de la propuesta | Estado | Acción |
|---|---|---|---|
| 1 | Transcripción audio → texto estructurado | ✅ | F9 + B4 hechos (diarización real = fleco) |
| 2 | Análisis con LLM (decisiones, acuerdos, roadmap) | ✅ | — |
| 3 | RAG sobre Markdown en Git (provenance) | ✅ | B1/B2/B7/B8 + sync hechos (filtros = fleco) |
| 4 | Generar actas + doc técnica + roadmap + ADRs | ✅ | F5 hecho |
| 5 | Human-in-the-loop (+ modo automático opcional) | ✅ | F7 + F8 hechos |
| 6 | UI: cargar audio, ver transcripciones, aprobar | ✅ | F4 + F11 hechos |
| 7 | Evaluación por métricas (WER, precisión, latencia, coste) | ✅ | F1 + F2 + F3 hechos |

Leyenda: ✅ hecho · 🟡 parcial · ❌ falta. **Los 7 objetivos de la propuesta están cubiertos.**

## 6. Criterio de éxito (para la memoria/defensa)

- `pytest`, `ruff` y `mypy` **verdes en CI** (multi-plataforma y multi-versión de Python).
- ≥ 1 flujo **E2E demostrable** con datos de ejemplo (sin depender de datos reales sensibles).
- **Métricas cuantitativas** de transcripción, extracción, RAG, latencia y coste, reproducibles.
- La **UI** permite revisar y validar documentos **con evidencias**.
- La **publicación Git** produce PRs **trazables y seguros**.
- La **documentación del repo coincide** con el comportamiento real del sistema.

## 7. Convenciones de trabajo

- **Una rama/PR por ítem** (`Bxx`/`TDxx`/`Fxx`), con su test cuando aplique.
- Mantener siempre **verde** `ruff` + `mypy --strict` + `pytest` (es la red de seguridad).
- Documentar decisiones grandes como **ADR del propio repo** (p.ej. versionar `uv.lock`, romper el ciclo de capas):
  encaja con la temática del proyecto y enriquece la memoria.
- Tras tocar comportamiento, **actualizar README/ARCHITECTURE** en el mismo PR.

## 8. Índice de documentos

- [`01-bugs-y-deuda-tecnica.md`](01-bugs-y-deuda-tecnica.md) — 12 bugs (`B1`–`B12`) + 13 ítems de deuda (`TD1`–`TD13`).
- [`02-features.md`](02-features.md) — 12 features (`F1`–`F12`) priorizadas para el TFM.
- [`../MEJORAS_PROYECTO.md`](../MEJORAS_PROYECTO.md) — análisis previo (superado por esta carpeta; conservado por contexto histórico).
