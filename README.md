# MeetingForge

Sistema de IA generativa para transcribir reuniones técnicas y extraer insights estructurados (decisiones, tareas, temas).

## Estado: Fase 4 — Human-in-the-loop + integración Git

Pipeline end-to-end con validación humana y publicación versionada:
**Audio → Transcripción (Whisper) → Retrieval (ChromaDB + sentence-transformers) → Insights con citas (LLM) → Generación de ADRs/Actas → UI Streamlit → Validación humana → Publicación Git + PR**.

## Setup

### Prerrequisitos

- Python 3.11, 3.12 o 3.13
- `ffmpeg` (necesario para faster-whisper)
- API key de Anthropic u OpenAI

### Windows (PowerShell)

```powershell
# Instalar uv (gestor de dependencias)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Instalar ffmpeg
winget install Gyan.FFmpeg

# Clonar e instalar dependencias
git clone <url> meeting-forge
cd meeting-forge
uv sync

# Configurar variables de entorno
Copy-Item .env.example .env
# Editar .env con tus API keys
```

### macOS / Linux

```bash
# Instalar uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Instalar ffmpeg (Mac)
brew install ffmpeg
# Instalar ffmpeg (Linux Debian/Ubuntu)
sudo apt install ffmpeg

# Instalar dependencias
uv sync
cp .env.example .env
```

## Uso

> **Entrypoints CLI** (tras `uv sync`): `meeting-forge run|index|eval|demo|check`. Son la forma
> recomendada de invocar el sistema instalado; equivalen a los scripts de `scripts/`.

### 0. Demo rápida y verificación (sin API keys)

```bash
# Verifica prerequisitos (Python, ffmpeg, gh, API keys)
uv run meeting-forge check

# Crea una reunión de demostración (sin LLM ni audio) y explórala en la UI
uv run meeting-forge demo
uv run --group ui streamlit run src/meeting_forge/ui/app.py
```

### 1. Indexar documentación (RAG)

Antes del E2E con RAG activado, indexa los Markdown del repo (+ `DOCS_PATH` si está configurado):

```bash
uv run python scripts/index_docs.py
# Para reindexar desde cero:
uv run python scripts/index_docs.py --clear
# Para añadir rutas extra:
uv run python scripts/index_docs.py --path C:/otros/docs --path C:/mas/docs
```

El índice persiste en `data/chromadb/`. Idempotente: ejecutarlo dos veces no duplica chunks.

### 2. Ejecutar pipeline E2E

```bash
# Con RAG (default si rag_enabled=true)
uv run python scripts/run_e2e.py data/raw/test_meeting.wav

# Sin RAG (Fase 0 behaviour)
uv run python scripts/run_e2e.py data/raw/test_meeting.wav --no-rag

# Con proveedor específico
LLM_PROVIDER=openai uv run python scripts/run_e2e.py data/raw/test_meeting.wav
```

El resultado se escribe en `data/outputs/<nombre>_result.json` e incluye `sources` (referencias path + líneas) en las decisiones y tareas fundamentadas en la documentación.

### 3. UI — visor de reuniones

```bash
# Instalar dependencias de UI (solo la primera vez)
uv sync --group ui

# Lanzar el visor
uv run --group ui streamlit run src/meeting_forge/ui/app.py
```

Desde el panel **➕ Procesar nueva reunión** (barra lateral) puedes **subir un audio y ejecutar el pipeline** (transcripción → RAG → extracción → generación) con progreso por fase, sin usar la terminal. Además, la UI navega los outputs ya procesados en `data/outputs/` y muestra: resumen ejecutivo, transcript con timestamps, decisiones y tareas con sus fuentes, panel de evidencia (texto real de los chunks citados) y los documentos generados (ADRs, actas, roadmap, doc técnica) con sus diffs.

### 4. Validación y publicación a Git

Desde la UI puedes revisar, editar, aprobar o rechazar cada documento generado, y publicarlos a un repositorio Git con PR automático:

**Prerrequisitos:**

- `gh` CLI instalado y autenticado (`gh auth login`)
- Variables de entorno en `.env`:

```env
GIT_INTEGRATION_ENABLED=true
GIT_TARGET_REPO_PATH=/ruta/al/repo/destino
GIT_BASE_BRANCH=main
GIT_BRANCH_PREFIX=meeting-forge/
```

**Flujo:**

1. Lanza la UI y selecciona una reunión con documentos generados.
2. En el panel "Documentos Generados" valida cada documento (Aprobar / Editar / Rechazar).
3. Con al menos un documento aprobado, pulsa "Publicar a Git".
4. La UI crea una rama, hace commit, push y abre un PR en el repositorio destino.

### 5. Evaluación (métricas)

Calcula métricas de calidad reproducibles a partir de un dataset anotado: WER (transcripción),
precision/recall/F1 (extracción) y precision@k/recall@k (retrieval).

```bash
uv run python scripts/evaluate.py evaluation/datasets/example.json --k 3
```

Escribe `evaluation/results/report.json` y `report.md` (tabla lista para anexos de la memoria).

Para añadir **coste y latencia reales** al reporte, pásale los `result.json` de ejecuciones del
pipeline con `--from-run` (repetible); agrega coste total/medio, latencia media de LLM y tokens
medios por run a partir de su telemetría (`run_meta`):

```bash
uv run meeting-forge eval evaluation/datasets/example.json --k 3 \
  --from-run data/outputs/<id>/<id>_result.json
```

Además, cada ejecución de `run_e2e.py` registra telemetría por run en `data/outputs/<id>/<id>_result.json`:

- `run_meta`: `run_id`, tiempos por fase, tokens de entrada/salida, latencia y coste estimado por proveedor.
- `meeting_metadata`: fecha/título/audio de la reunión (usados por la UI al publicar).
- `retrieved_evidence`: texto + score de los chunks recuperados (evidencia reproducible).

## Tests

```bash
# Tests unitarios (rápidos, sin red)
uv run pytest

# Con coverage
uv run pytest --cov=meeting_forge --cov-report=html

# Tests de integración (skipped por defecto; requieren fixtures, modelos y API keys).
# Habilítalos definiendo RUN_INTEGRATION:
RUN_INTEGRATION=1 uv run pytest -m integration
```

## Comandos útiles

```bash
# Linting y formato
uv run ruff check .
uv run ruff format .

# Type checking
uv run mypy src/

# Añadir dependencia
uv add <package>

# Pre-commit
uv run pre-commit install
uv run pre-commit run --all-files
```

## Estructura del proyecto

```text
meeting-forge/
├── src/meeting_forge/   # Paquete principal
│   ├── ingestion/       # Transcripción (Whisper)
│   ├── analysis/        # Extracción con LLMs
│   ├── rag/             # (Fase 1)
│   ├── generation/      # (Fase 2)
│   ├── ui/              # (Fase 3)
│   ├── git_integration/ # (Fase 4)
│   └── validation/      # (Fase 4)
├── prompts/             # Prompts versionados
├── scripts/             # CLI y utilidades
├── tests/               # Unit + integration
├── data/                # Audios, transcripciones, outputs (gitignored)
└── evaluation/          # Datasets y métricas
```

Ver [`ARCHITECTURE.md`](ARCHITECTURE.md) para detalles de arquitectura y decisiones técnicas.

## Roadmap

- [x] **Fase 0**: Walking skeleton (transcripción + extracción básica)
- [x] **Fase 1**: RAG sobre documentación Markdown (provenance con `sources`)
- [x] **Fase 2**: Generación de ADRs y actas
- [x] **Fase 3**: UI Streamlit (visor de reuniones procesadas)
- [x] **Fase 4**: Human-in-the-loop + integración Git
