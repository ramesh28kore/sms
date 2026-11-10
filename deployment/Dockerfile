# Avanthi Attendance — Docker image
# Multi-stage: 'builder' compiles Tailwind CSS; 'production' is the runtime image.

ARG PYTHON_VERSION=3.13

# ---- Stage 1: Tailwind CSS build ----
FROM node:22-alpine AS tailwind-builder
WORKDIR /app
COPY src/static_src/package.json src/static_src/package-lock.json* ./
RUN npm ci --ignore-scripts
COPY src/static_src/ ./
RUN npm run build

# ---- Stage 2: Python dependency install ----
FROM python:${PYTHON_VERSION}-slim AS python-builder
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip wheel --no-deps --wheel-dir /wheels -r requirements.txt

# ---- Stage 3: Production image ----
FROM python:${PYTHON_VERSION}-slim AS production
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DJANGO_SETTINGS_MODULE=config.settings.production
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 wget \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --gid 1001 appgroup \
    && adduser --uid 1001 --gid 1001 --disabled-password --no-create-home appuser

COPY --from=python-builder /wheels /wheels
RUN pip install --no-index --no-cache-dir --find-links=/wheels /wheels/*.whl && rm -rf /wheels

# Copy application source
COPY src/ ./
COPY --from=tailwind-builder /app/dist/ ./static_src/dist/

RUN mkdir -p /app/media /app/staticfiles \
    && chown -R appuser:appgroup /app

USER appuser
EXPOSE 8000

