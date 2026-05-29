FROM python:3.12-slim

ARG UV_VERSION=0.11.8

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_LINK_MODE=copy
ENV PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

RUN pip install --no-cache-dir "uv==${UV_VERSION}"

COPY pyproject.toml uv.lock ./
COPY packages ./packages

RUN uv sync --package dossieragent-core --locked --no-dev

EXPOSE 8000

CMD ["python", "-m", "dossieragent_core.api", "--host", "0.0.0.0", "--port", "8000"]
