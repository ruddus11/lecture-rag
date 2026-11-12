# 빌드 컨텍스트는 저장소 루트 (evaluation/, config/ 를 함께 복사하기 위해)
FROM python:3.12.16-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df

COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --python /usr/local/bin/python3.12

COPY apps/api/app ./app
COPY apps/api/scripts ./scripts
COPY evaluation ./evaluation
COPY config ./config
COPY infra/opensearch/index-chunks.json ./infra/opensearch/index-chunks.json

RUN useradd --create-home --uid 10001 app \
 && mkdir -p /data /home/app/.cache/huggingface /app/evaluation/results \
 && chown -R app:app /data /home/app /app/evaluation/results

ARG APP_COMMIT=unknown
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app \
    HF_HOME=/home/app/.cache/huggingface \
    APP_COMMIT=$APP_COMMIT

USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live', timeout=3).status == 200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
