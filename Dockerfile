FROM python:3.12.8-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY proofloop ./proofloop
COPY templates ./templates
COPY static ./static
COPY data ./data
COPY README.md LICENSE .env.example ./

RUN mkdir -p /app/data && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["sh", "-c", "uvicorn proofloop.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
