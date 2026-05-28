# syntax=docker/dockerfile:1.7
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps: opencv runtime libs + curl for healthcheck + build tools for any wheels w/o manylinux.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        curl \
        libgl1 \
        libglib2.0-0 \
        build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app/apps/backend

# Pre-install CPU-only torch BEFORE requirements.txt so ultralytics doesn't pull the CUDA wheel.
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
        torch==2.5.1 torchvision==0.20.1

# Copy only requirements first for better layer caching.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Backend source.
COPY app ./app
COPY pytest.ini ./

# Create a non-root runtime user and hand it ownership of the app + storage
# paths (audit DCK-MAJ-3). System ultralytics weights are downloaded into the
# user's home directory on first use, so the home must exist and be writable.
RUN groupadd --system papi \
 && useradd --system --gid papi --create-home --shell /usr/sbin/nologin papi \
 && mkdir -p /storage /models \
 && chown -R papi:papi /app /storage /models /home/papi

ENV PAPI_MODEL_PATH=/models/serving/best.pt \
    PAPI_STORAGE_DIR=/storage \
    DATABASE_URL=postgresql+psycopg://papi:papi@postgres:5432/papi_backend

USER papi

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
