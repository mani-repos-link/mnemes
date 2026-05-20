FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY apps/pyapi/pyproject.toml apps/pyapi/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir sqliteai-vector>=0.9.0

COPY apps/pyapi/pyapi ./pyapi

RUN useradd --create-home --uid 1000 mnemes && \
    mkdir -p /data && chown -R mnemes:mnemes /data /app
USER mnemes

ENV APP_ADDR=:8080 \
    DATABASE_URL=file:/data/chatbot.sqlite

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "pyapi.main:app", "--host", "0.0.0.0", "--port", "8080"]
