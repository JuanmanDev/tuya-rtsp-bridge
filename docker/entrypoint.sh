#!/bin/sh
# Fix ownership of bind-mounted /data and /config (created as root by Docker on
# Linux hosts), then drop privileges to the unprivileged bridge user.
# PUID / PGID override the uid/gid the app runs as (default 1000:1000).
set -e

if [ "$(id -u)" = "0" ]; then
  PUID="${PUID:-1000}"
  PGID="${PGID:-1000}"
  mkdir -p "${XDG_DATA_HOME:-/data}/tuya-rtsp-bridge" "${XDG_CONFIG_HOME:-/config}/tuya-rtsp-bridge"
  chown -R "${PUID}:${PGID}" "${XDG_DATA_HOME:-/data}" "${XDG_CONFIG_HOME:-/config}" 2>/dev/null || true
  exec setpriv --reuid="${PUID}" --regid="${PGID}" --clear-groups -- "$@"
fi

exec "$@"
