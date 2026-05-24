# MeetingForge

Sistema de IA generativa para transcribir reuniones técnicas y extraer insights estructurados (decisiones, tareas, temas).

## Estado: Fase 0 — Walking Skeleton

Pipeline end-to-end: **Audio → Transcripción (Whisper) → Insights (LLM) → JSON estructurado**.

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

```bash
# Ejecutar pipeline E2E
uv run python scripts/run_e2e.py data/raw/test_meeting.wav

# Con proveedor específico (sobreescribiendo .env)
LLM_PROVIDER=openai uv run python scripts/run_e2e.py data/raw/test_meeting.wav
```

El resultado se escribe en `data/outputs/<nombre>_result.json`.

## Tests

```bash
# Tests unitarios (rápidos, sin red)
uv run pytest

# Con coverage
uv run pytest --cov=meeting_forge --cov-report=html

# Tests de integración (requieren fixture y API keys, skipped por defecto)
uv run pytest -m integration --no-skip
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

```
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
- [ ] **Fase 1**: RAG sobre documentación Markdown
- [ ] **Fase 2**: Generación de ADRs y actas
- [ ] **Fase 3**: UI Streamlit
- [ ] **Fase 4**: Human-in-the-loop + integración Git
