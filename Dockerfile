# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.13
FROM ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-bookworm-slim AS base

ENV PYTHONUNBUFFERED=1

ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/app" \
    --shell "/sbin/nologin" \
    --uid "${UID}" \
    appuser

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    python3-dev \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- deps first (cache-friendly) ---
COPY pyproject.toml uv.lock ./
RUN mkdir -p src
RUN uv sync --locked

# --- app files (now includes vectorstore) ---
COPY . .

# ✅ bake the FAISS index into the image
# Make sure vectorstore/ (with index.faiss and index.pkl) exists at repo root and is NOT in .dockerignore
# COPY is redundant if you're already doing COPY . . above, but we add ENV and ensure path
ENV VECTORSTORE_PATH=/app/vectorstore

RUN chown -R appuser:appuser /app
USER appuser

# ⛔ If you don't need model downloads at build time, skip this line
# It was causing builds to fail when optional plugins aren't installed
# RUN uv run src/agent.py download-files

# Start the worker
CMD ["uv", "run", "src/agent.py", "start"]
