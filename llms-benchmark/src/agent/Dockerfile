# llmbench-agent - the pydantic-ai agent of the llms-benchmark demo.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /srv
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

EXPOSE 8080
CMD ["python", "-m", "app.main"]
