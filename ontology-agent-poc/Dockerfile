FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ONTOLOGY_AGENT_PROJECT_ROOT=/app \
    PATH=/app/.venv/bin:$PATH

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN python -m pip install uv==0.6.5 \
    && uv sync --frozen --no-dev --no-install-project \
    && uv pip install "hatchling>=1.27,<2"

COPY src ./src
RUN uv sync --frozen --no-dev --no-editable --offline --no-build-isolation

COPY scripts ./scripts
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
COPY scenarios ./scenarios
COPY skills ./skills

RUN python scripts/generate_fixtures.py \
    && addgroup --system --gid 10001 app \
    && adduser --system --uid 10001 --ingroup app app \
    && mkdir -p /app/outputs/executions /app/published /app/studio \
    && chown -R app:app /app/outputs /app/published /app/studio

USER app
EXPOSE 8790 8791 8792 8793 8794

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8790/api/healthz', timeout=2)"

CMD ["uvicorn", "ontology_agent.api:app", "--host", "0.0.0.0", "--port", "8790"]
