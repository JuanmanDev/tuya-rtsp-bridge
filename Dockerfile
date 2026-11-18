# syntax=docker/dockerfile:1
# Headless API + RTSP engine. No VLC, no desktop GUI.
# Multi-arch: the Go engine is cross-compiled on the build host (no QEMU for Go).

FROM --platform=$BUILDPLATFORM golang:1.27-trixie AS engine
ARG TARGETOS
ARG TARGETARCH
ARG TARGETVARIANT
WORKDIR /src
COPY vendor/tuya-ipc-terminal/go.mod vendor/tuya-ipc-terminal/go.sum ./
RUN go mod download
COPY vendor/tuya-ipc-terminal/ ./
RUN CGO_ENABLED=0 GOOS=${TARGETOS:-linux} GOARCH=${TARGETARCH:-amd64} \
    GOARM="$(echo "${TARGETVARIANT}" | tr -d v)" \
    go build -trimpath -ldflags="-s -w" -o /out/tuya-ipc-terminal .

FROM python:3.14-slim-trixie
ARG APP_VERSION=dev
LABEL org.opencontainers.image.title="Tuya RTSP Bridge" \
      org.opencontainers.image.description="Turn Tuya / Smart Life cameras into plain RTSP for Frigate, go2rtc, Agent DVR." \
      org.opencontainers.image.source="https://github.com/JuanmanDev/tuya-rtsp-bridge" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${APP_VERSION}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates procps \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin bridge

WORKDIR /app
COPY requirements-docker.txt /app/requirements-docker.txt
RUN pip install --no-cache-dir -r /app/requirements-docker.txt

COPY src /app/src
COPY web /app/web
COPY --from=engine /out/tuya-ipc-terminal /app/bin/tuya-ipc-terminal
COPY docker/entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 755 /app/bin/tuya-ipc-terminal /usr/local/bin/docker-entrypoint.sh \
    && mkdir -p /data/tuya-rtsp-bridge /config/tuya-rtsp-bridge \
    && chown -R bridge:bridge /app /data /config

ENV TUYA_BRIDGE_ROOT=/app \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    XDG_DATA_HOME=/data \
    XDG_CONFIG_HOME=/config \
    PATH="/app/bin:${PATH}" \
    HOME=/home/bridge

# Starts as root only to chown bind mounts, then drops to uid PUID (default 1000).
EXPOSE 8787 8554
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/api/state', timeout=3)"

WORKDIR /data/tuya-rtsp-bridge
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "-u", "/app/src/server.py"]
