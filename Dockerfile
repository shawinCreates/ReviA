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

# unstructured[pdf] pulls the GUI build of opencv, whose module imports cv2 even
# for the "fast" partitioning strategy this image uses. cv2 links against X11/GL
# libraries that the slim base omits, so install them. Kept as its own late
# layer: extending the libgomp install above would invalidate the cached
# dependency and model layers and re-download both on every build.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0t64 libsm6 libxext6 libxrender1 libxfixes3 libice6 libx11-6 \
        libxcb1 libxcb-shm0 libxcb-render0 libxcb-xfixes0 libxcb-randr0 \
    && rm -rf /var/lib/apt/lists/*

# Put the venv on PATH so the CMD's `gunicorn` resolves; `uv sync` installs it
# to /app/.venv/bin and nothing else adds it. Set after the dependency layers so
# changing it does not invalidate the cached install above.
ENV PATH="/app/.venv/bin:$PATH"

COPY backend backend

WORKDIR /app/backend
EXPOSE 8000

# One worker on purpose: the in-process model plus the advisory-lock pipeline
# worker want a single process, and the free tier has 512 MB of RAM.
CMD ["/bin/sh", "-c", "gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 4 --access-logfile -"]