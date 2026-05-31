FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

COPY requirements.lock ./requirements.lock
RUN pip install --no-cache-dir -r requirements.lock

COPY alembic.ini ./alembic.ini
COPY app ./app
COPY migrations ./migrations
COPY docker-entrypoint.sh ./docker-entrypoint.sh

RUN useradd --create-home --shell /usr/sbin/nologin orbis \
    && chmod +x /app/docker-entrypoint.sh \
    && chown -R orbis:orbis /app
USER orbis

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=300s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/health', timeout=5).read()"

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
