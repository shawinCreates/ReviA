FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Dependencies first, so this layer stays cached while the code changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# unstructured[pdf] pulls the GUI build of opencv, which imports cv2 even for
# the "fast" partition strategy this image uses; cv2 needs the X11/GL libs.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0t64 libsm6 libxext6 libxrender1 libxfixes3 libice6 libx11-6 \
        libxcb1 libxcb-shm0 libxcb-render0 libxcb-xfixes0 libxcb-randr0 \
    && rm -rf /var/lib/apt/lists/*

# Put the venv on PATH so the CMD's `gunicorn` resolves; set after the
# dependency layers so changing it does not invalidate the cached install.
ENV PATH="/app/.venv/bin:$PATH"

COPY backend backend

WORKDIR /app/backend
EXPOSE 8000

# One worker (the advisory-lock pipeline worker wants a single process; 512MB tier).
CMD ["/bin/sh", "-c", "gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 4 --access-logfile -"]

# Pre-install spaCy model to avoid runtime downloads
RUN python -m spacy download en_core_web_sm==3.8.0 || true

# Set environment variables to help with model caching
ENV HF_HOME=/app/.cache/huggingface \
    TRANSFORMERS_CACHE=/app/.cache/huggingface \
    UNSTRUCTURED_CACHE_DIR=/app/.cache/unstructured \
    XDG_CACHE_HOME=/app/.cache

# Increase gunicorn timeout for slow document parsing
CMD ["/bin/sh", "-c", "gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 4 --timeout 600 --graceful-timeout 300 --keep-alive 5 --access-logfile -"]

# Create cache directories
RUN mkdir -p /app/.cache/huggingface /app/.cache/unstructured
