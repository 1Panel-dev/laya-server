FROM node:24-bookworm-slim AS frontend-build
WORKDIR /app/frontend
RUN npm install -g pnpm@11.19.0
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN CI=true pnpm install --frozen-lockfile
COPY frontend/ ./
RUN CI=true pnpm build

FROM debian:bookworm-slim AS upstream-check
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
COPY laya/ /upstream/
ARG LAYA_UPSTREAM_SHA=010bacef009c855ccba814b51f7c8e1d38ab5e3f
RUN test "$(git -C /upstream rev-parse HEAD)" = "$LAYA_UPSTREAM_SHA" && \
    test -z "$(git -C /upstream status --porcelain)" || \
    (echo 'Laya checkout must match the pinned SHA and be clean' >&2; exit 1)

FROM python:3.12-slim AS model-download
ENV LAYA_MODEL_DIR=/opt/model-download HF_HOME=/opt/hf-cache
WORKDIR /app
RUN pip install --no-cache-dir huggingface-hub==0.29.3
COPY scripts/download-models.py /app/scripts/download-models.py
RUN python /app/scripts/download-models.py --model multilingual && \
    test -s /opt/model-download/multilingual/model.safetensors

FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    LAYA_DATABASE_PATH=/data/laya.sqlite3 LAYA_MODEL_DIR=/opt/models \
    LAYA_MODEL_PROFILE=multilingual LAYA_FRONTEND_DIR=/app/frontend/dist \
    HF_HOME=/data/hf-cache HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
WORKDIR /app
RUN pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir transformers==4.48.3 safetensors==0.5.3 huggingface-hub==0.29.3 numpy==1.26.4
COPY --from=upstream-check /upstream/pyproject.toml /upstream/README.md /upstream/LICENSE /opt/laya/
COPY --from=upstream-check /upstream/laya/ /opt/laya/laya/
RUN pip install --no-cache-dir --no-deps /opt/laya
COPY backend/ /app/backend/
RUN pip install --no-cache-dir /app/backend
COPY --from=model-download /opt/model-download/multilingual/ /opt/models/multilingual/
COPY scripts/smoke-image-model.py /app/scripts/smoke-image-model.py
COPY --from=frontend-build /app/frontend/dist/ /app/frontend/dist/
RUN mkdir -p /data && python /app/scripts/smoke-image-model.py
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/live', timeout=3)" || exit 1
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--proxy-headers"]
