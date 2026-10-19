FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 PORT=7860 KB_DIR=/app/data/kb \
    CACHE_DIR=/app/data/cache JOB_DB=/app/data/state/jobs.sqlite3
WORKDIR /app
COPY src/mvp/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home app \
    && mkdir -p /app/data/state \
    && chown -R app:app /app/data
COPY src /app/src
USER app
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/healthz', timeout=3)"
CMD ["python", "-m", "src.mvp.app"]
