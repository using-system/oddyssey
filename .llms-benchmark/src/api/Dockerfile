# llmbench-api - the catalog and orders API of the llms-benchmark demo.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CATALOG_DB_PATH=/data/catalog.db

WORKDIR /srv
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir . && mkdir -p /data

EXPOSE 8000
CMD ["python", "-m", "app.main"]
