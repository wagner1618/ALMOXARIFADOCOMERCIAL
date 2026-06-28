# syntax=docker/dockerfile:1

# ----- Imagem base ---------------------------------------------------------
FROM python:3.12-slim AS base

# Dependências de sistema do WeasyPrint (PDF) + libpq para o psycopg.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq5 \
        libcairo2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        libffi-dev \
        shared-mime-info \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    FLASK_ENV=production

WORKDIR /app

# ----- Dependências (camada cacheável) ------------------------------------
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install ".[pdf]"

# ----- Código da aplicação -------------------------------------------------
COPY . .

# Usuário não-root
RUN useradd --create-home --uid 10001 almox \
    && mkdir -p /app/instance /app/app/static/uploads \
    && chown -R almox:almox /app
USER almox

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

# entrypoint aplica migrações antes de subir o Gunicorn
COPY --chown=almox:almox docker/entrypoint.sh /app/docker/entrypoint.sh
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "wsgi:app", "-w", "4", "-b", "0.0.0.0:8000", "--access-logfile", "-"]
