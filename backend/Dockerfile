FROM ghcr.io/astral-sh/uv:0.9.26 AS uv

FROM python:3.12.10-slim-bookworm

COPY --from=uv /uv /uvx /bin/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-cache --no-dev --no-install-project

COPY app ./app

RUN useradd --system --uid 10001 --no-create-home appuser
USER appuser

CMD ["python", "-m", "app"]
