FROM mcr.microsoft.com/playwright/python:v1.60.0-noble

ARG UV_VERSION=0.11.8

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_LINK_MODE=copy
ENV PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

RUN pip install --no-cache-dir "uv==${UV_VERSION}"

COPY pyproject.toml uv.lock ./
COPY packages ./packages

RUN uv sync --package dossieragent-browser --locked --no-dev

CMD ["python", "-m", "dossieragent_browser.worker", "--artifact-dir", "/app/storage/browser"]
