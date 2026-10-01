# syntax=docker/dockerfile:1

FROM python:3.14-slim-trixie AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
# GeoDjango needs GDAL, GEOS and PROJ shared libraries (pulled in by gdal-bin).
RUN apt-get update \
    && apt-get install -y --no-install-recommends gdal-bin binutils \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app

FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv
COPY pyproject.toml uv.lock ./
# "--no-dev" for production images; compose passes an empty value to include dev tools.
ARG UV_SYNC_ARGS="--no-dev"
RUN uv sync --frozen --no-install-project ${UV_SYNC_ARGS}

FROM base AS runtime
RUN useradd --create-home --uid 1000 app
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
COPY --chown=app:app . .
USER app
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
