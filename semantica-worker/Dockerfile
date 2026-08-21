FROM python:3.12-slim-bookworm@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134

ARG SEMANTICA_COMMIT=c5d382ee81edc0727d07907c932970c762ec33bd

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SEMANTICA_DISABLE_PROGRESS=1 \
    SEMANTICA_DISABLE_JUPYTER_PROGRESS=1

WORKDIR /worker

RUN pip install --no-cache-dir \
      "fastapi>=0.141,<1" \
      "pydantic>=2.13,<3" \
      "rdflib>=7.6,<8" \
      "PyYAML>=6,<7" \
      "uvicorn>=0.52,<1" \
  && pip install --no-cache-dir --no-deps \
      "https://github.com/semantica-agi/semantica/archive/${SEMANTICA_COMMIT}.tar.gz"

COPY pyproject.toml ./pyproject.toml
COPY src ./src
COPY THIRD_PARTY_NOTICES.md ./THIRD_PARTY_NOTICES.md
RUN pip install --no-cache-dir --no-deps .

RUN useradd --create-home --uid 10001 worker
USER 10001

EXPOSE 8795
CMD ["uvicorn", "ontology_semantica_worker.app:app", "--host", "0.0.0.0", "--port", "8795", "--no-access-log"]
