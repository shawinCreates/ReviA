FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    EMBEDDING_CACHE_DIR=/app/.cache/model

# libgomp is the OpenMP runtime that fastembed's ONNX Runtime requires.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, so this layer stays cached while the code changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Bake the embedding model into the image. The free Render tier has an
# ephemeral disk, so the ~130 MB model must not be re-downloaded on every cold
# start, and the cache dir points at this copy.
RUN uv run python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/app/.cache/model')"

COPY backend backend

WORKDIR /app/backend
EXPOSE 8000

# One worker on purpose: the in-process model plus the advisory-lock pipeline
# worker want a single process, and the free tier has 512 MB of RAM.
CMD ["/bin/sh", "-c", "gunicorn config.wsgi.application --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 4 --access-logfile -"]