#!/bin/sh
set -eu

APP_USER=appuser
APP_GROUP=appgroup

# PUID/PGID only work when this entrypoint runs as root first. It chowns
# /app/config and /app/data, then drops privileges with setpriv(1) from
# util-linux (same idea as gosu, but no passwd/libcontainer quirks for numeric
# uid/gid). If the container starts already non-root (docker-compose user:,
# Kubernetes runAsUser, etc.), chown/drop is skipped.

if [ "$(id -u)" = "0" ] && [ "${PUID:-0}" != "0" ]; then
    if ! getent group "${PGID}" >/dev/null 2>&1; then
        groupadd --gid "${PGID}" "${APP_GROUP}"
    fi

    if ! getent passwd "${PUID}" >/dev/null 2>&1; then
        useradd \
            --uid "${PUID}" \
            --gid "${PGID}" \
            --home-dir /app/data \
            --no-create-home \
            --shell /usr/sbin/nologin \
            "${APP_USER}"
    fi

    mkdir -p /app/data/.cache
    if ! chown -R "${PUID}:${PGID}" /app/config /app/data; then
        echo "hades-ii-run-tracker: ERROR: chown ${PUID}:${PGID} on /app/config and /app/data failed." >&2
        echo "  On the host, try: chown -R ${PUID}:${PGID} ./data and the mounted config file," >&2
        echo "  or run with PUID=0 PGID=0 (not recommended)." >&2
        exit 1
    fi

    export HOME=/app/data
    export XDG_CACHE_HOME=/app/data/.cache

    if ! command -v setpriv >/dev/null 2>&1; then
        echo "hades-ii-run-tracker: ERROR: setpriv not found (install util-linux)." >&2
        exit 1
    fi

    if [ -n "${HADES_ENTRYPOINT_DEBUG:-}" ]; then
        echo "hades-ii-run-tracker: setpriv --reuid=${PUID} --regid=${PGID} (HOME=$HOME)" >&2
    fi

    # --clear-groups: only PGID as primary group (matches chown target).
    exec setpriv \
        --reuid="${PUID}" \
        --regid="${PGID}" \
        --clear-groups \
        -- "$@"
fi

if [ "$(id -u)" != "0" ]; then
    echo "hades-ii-run-tracker: WARNING: running as UID $(id -u) GID $(id -g), not root." >&2
    echo "  PUID/PGID were not applied (setpriv + chown require starting as root)." >&2
    echo "  Remove docker-compose user:/Kubernetes runAsUser, or chown volumes to $(id -u):$(id -g)." >&2
    export HOME=/app/data
    export XDG_CACHE_HOME=/app/data/.cache
    mkdir -p /app/data/.cache 2>/dev/null || true
fi

exec "$@"
