# syntax=docker/dockerfile:1.7

FROM python:3.11-slim AS cpu-runtime

ARG APP_VERSION=0.5.2
ARG TORCH_CPU_INDEX_URL=https://download.pytorch.org/whl/cpu
ARG TORCH_CPU_VERSION=2.11.0+cpu
ARG TORCHAUDIO_CPU_VERSION=2.11.0+cpu
LABEL org.opencontainers.image.title="Shuyi Agent" \
      org.opencontainers.image.version="$APP_VERSION"
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/home/shuyi \
    HF_HOME=/models/.cache/huggingface \
    MODELSCOPE_CACHE=/models/.cache/modelscope \
    SHUYI_DATA_DIR=/data \
    SHUYI_MODEL_DIR=/models
RUN groupadd --system shuyi \
    && useradd --system --gid shuyi --create-home shuyi \
    && apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg libsndfile1 sox \
    && rm -rf /var/lib/apt/lists/*
ENV SHUYI_REQUIRE_TTS_READY=0
WORKDIR /app
COPY scripts/container/requirements-runtime.txt /tmp/requirements-runtime.txt
RUN python -m pip install --no-cache-dir \
        "torch==$TORCH_CPU_VERSION" \
        "torchaudio==$TORCHAUDIO_CPU_VERSION" \
        --index-url "$TORCH_CPU_INDEX_URL" \
    && python -m pip install --no-cache-dir -r /tmp/requirements-runtime.txt
COPY backend /app/backend
COPY scripts /app/scripts
COPY assets /app/assets
RUN mkdir -p /data/outputs /models \
    && ln -s /data/outputs /app/outputs \
    && chown -R shuyi:shuyi /data /models /home/shuyi \
    && chmod +x /app/scripts/container/entrypoint.sh /app/scripts/container/download_models.py
USER shuyi
VOLUME ["/data", "/models"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=5m --retries=10 \
  CMD ["python", "/app/scripts/container/healthcheck.py"]
ENTRYPOINT ["/app/scripts/container/entrypoint.sh"]
CMD []

FROM pytorch/pytorch:2.7.1-cuda12.8-cudnn9-runtime AS cuda-runtime

ARG APP_VERSION=0.5.2
LABEL org.opencontainers.image.title="Shuyi Agent CUDA" \
      org.opencontainers.image.version="$APP_VERSION"
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/home/shuyi \
    HF_HOME=/models/.cache/huggingface \
    MODELSCOPE_CACHE=/models/.cache/modelscope \
    SHUYI_DATA_DIR=/data \
    SHUYI_MODEL_DIR=/models \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility
RUN groupadd --system shuyi \
    && useradd --system --gid shuyi --create-home shuyi \
    && apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg libsndfile1 sox \
    && rm -rf /var/lib/apt/lists/*
ENV SHUYI_REQUIRE_TTS_READY=0
WORKDIR /app
COPY scripts/container/requirements-runtime.txt /tmp/requirements-runtime.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements-runtime.txt
COPY backend /app/backend
COPY scripts /app/scripts
COPY assets /app/assets
RUN mkdir -p /data/outputs /models \
    && ln -s /data/outputs /app/outputs \
    && chown -R shuyi:shuyi /data /models /home/shuyi \
    && chmod +x /app/scripts/container/entrypoint.sh /app/scripts/container/download_models.py
USER shuyi
VOLUME ["/data", "/models"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=5m --retries=10 \
  CMD ["python", "/app/scripts/container/healthcheck.py"]
ENTRYPOINT ["/app/scripts/container/entrypoint.sh"]
CMD []
