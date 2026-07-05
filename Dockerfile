# MeetingForge — imagen reproducible para CLI y UI (M3 · cierra el fleco F10).
#
# Build:  docker build -t meeting-forge .
# UI:     docker run --rm -p 8501:8501 --env-file .env meeting-forge
# CLI:    docker run --rm --env-file .env meeting-forge uv run meeting-forge check
#
# Nota: los modelos de Whisper y de embeddings se descargan en el primer uso. Para no re-descargarlos
# en cada arranque, monta un volumen en la caché de Hugging Face, p.ej.:
#   docker run --rm -p 8501:8501 --env-file .env -v hf-cache:/root/.cache meeting-forge
FROM python:3.12-slim

# ffmpeg es obligatorio para faster-whisper; git habilita la integración Git de publicación.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg git \
    && rm -rf /var/lib/apt/lists/*

# uv: gestor de dependencias (binario desde la imagen oficial).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

# 1) Capa de dependencias (cacheable): se reinstala solo si cambian pyproject/uv.lock.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-install-project --group ui

# 2) Código del proyecto + instalación final (respetando el lockfile versionado · reproducibilidad TFM).
COPY src ./src
COPY prompts ./prompts
RUN uv sync --locked --group ui

# Por defecto lanza la UI Streamlit; sobreescribe el comando para usar el CLI
# (run / index / eval / demo / check), p.ej. `... meeting-forge uv run meeting-forge demo`.
EXPOSE 8501
CMD ["uv", "run", "--group", "ui", "streamlit", "run", "src/meeting_forge/ui/app.py", \
     "--server.address=0.0.0.0", "--server.port=8501"]
