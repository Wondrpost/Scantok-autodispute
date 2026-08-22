# Build from the repository root:
#   docker build -f docker/backend.Dockerfile -t auto-dispute-backend:latest .

FROM python:3.11-slim

# libgl1 + libglib2.0-0 are linked by opencv even in headless builds;
# libgomp1 is the OpenMP runtime torch/numpy/opencv all rely on.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/srv

EXPOSE 8000

RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /srv
USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
