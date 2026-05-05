#!/bin/sh
set -eu

APP_USER=appuser
APP_GROUP=appgroup

if [ "$(id -u)" = "0" ] && [ "${PUID:-0}" != "0" ]; then
    if ! getent group "${PGID}" >/dev/null 2>&1; then
        groupadd --gid "${PGID}" "${APP_GROUP}"
    fi

    APP_GROUP_NAME="$(getent group "${PGID}" | cut -d: -f1)"

    if ! getent passwd "${PUID}" >/dev/null 2>&1; then
        useradd \
            --uid "${PUID}" \
            --gid "${PGID}" \
            --home-dir /app/data \
            --no-create-home \
            --shell /usr/sbin/nologin \
            "${APP_USER}"
    fi

    APP_USER_NAME="$(getent passwd "${PUID}" | cut -d: -f1)"

    mkdir -p /app/data/.cache
    chown -R "${APP_USER_NAME}:${APP_GROUP_NAME}" /app/config /app/data \
        || echo "Warning: could not update ownership for /app/config or /app/data"

    # /app is root-owned; only config/data are chowned. If HOME=/app, tools that
    # write under ~/app (e.g. $HOME/app) hit Permission denied on /app/app.
    exec gosu "${APP_USER_NAME}:${APP_GROUP_NAME}" \
        env HOME=/app/data XDG_CACHE_HOME=/app/data/.cache \
        "$@"
fi

exec "$@"
