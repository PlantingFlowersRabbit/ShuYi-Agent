# syntax=docker/dockerfile:1.7

FROM python:3.11-slim AS cpu-runtime

ARG APP_VERSION=0.4.0
ARG TORCH_CPU_INDEX_URL=https://download.pytorch.org/whl/cpu
LABEL org.opencontainers.image.title="Shuyi Agent" \
      org.opencontainers.image.version="$APP_VERSION"
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/home/novelvoice \
    NOVELVOICE_DATA_DIR=/data \
    NOVELVOICE_MODEL_DIR=/models
RUN groupadd --system novelvoice \
    && useradd --system --gid novelvoice --create-home novelvoice \
    && apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY scripts/container/requirements-runtime.txt /tmp/requirements-runtime.txt
RUN python -m pip install --no-cache-dir torch --index-url "$TORCH_CPU_INDEX_URL" \
    && python -m pip install --no-cache-dir -r /tmp/requirements-runtime.txt
COPY backend /app/backend
COPY scripts /app/scripts
RUN mkdir -p /data/outputs /models \
    && ln -s /data/outputs /app/outputs \
    && chown -R novelvoice:novelvoice /data /models /home/novelvoice \
    && chmod +x /app/scripts/container/entrypoint.sh /app/scripts/container/download_models.py
USER novelvoice
VOLUME ["/data", "/models"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=5m --retries=10 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=5)" || exit 1
ENTRYPOINT ["/app/scripts/container/entrypoint.sh"]
CMD []

FROM pytorch/pytorch:2.7.1-cuda12.8-cudnn9-runtime AS cuda-runtime

ARG APP_VERSION=0.4.0
LABEL org.opencontainers.image.title="Shuyi Agent CUDA" \
      org.opencontainers.image.version="$APP_VERSION"
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/home/novelvoice \
    NOVELVOICE_DATA_DIR=/data \
    NOVELVOICE_MODEL_DIR=/models \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility
RUN groupadd --system novelvoice \
    && useradd --system --gid novelvoice --create-home novelvoice \
    && apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY scripts/container/requirements-runtime.txt /tmp/requirements-runtime.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements-runtime.txt
COPY backend /app/backend
COPY scripts /app/scripts
RUN mkdir -p /data/outputs /models \
    && ln -s /data/outputs /app/outputs \
    && chown -R novelvoice:novelvoice /data /models /home/novelvoice \
    && chmod +x /app/scripts/container/entrypoint.sh /app/scripts/container/download_models.py
USER novelvoice
VOLUME ["/data", "/models"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=5m --retries=10 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=5)" || exit 1
ENTRYPOINT ["/app/scripts/container/entrypoint.sh"]
CMD []
