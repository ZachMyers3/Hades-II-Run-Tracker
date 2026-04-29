FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HADES_CONFIG_PATH=/app/config/config.json
ENV HADES_DATA_PATH=/app/data/runs.json

WORKDIR /app

RUN mkdir -p /app/config /app/data

COPY pyproject.toml README.md ./
COPY src ./src
COPY config.example.json /app/config/config.json

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "hades_ii_run_tracker.app:app", "--host", "0.0.0.0", "--port", "8000"]
