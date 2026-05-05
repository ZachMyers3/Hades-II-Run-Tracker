FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HADES_CONFIG_PATH=/app/config/config.json
ENV HADES_DATA_PATH=/app/data/runs.json
ENV HADES_DATABASE_URL=sqlite:///app/data/hades.sqlite
ENV PUID=1000
ENV PGID=1000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/config /app/data

COPY pyproject.toml README.md ./
COPY src ./src
COPY config.example.json /app/config/config.json
COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN pip install --no-cache-dir . \
    && chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "hades_ii_run_tracker.app:app", "--host", "0.0.0.0", "--port", "8000"]
