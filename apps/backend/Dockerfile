# syntax=docker/dockerfile:1.7

# ---- builder stage --------------------------------------------------------
# Compiles/installs the Python dependency tree into a self-contained venv.
# build-essential lives ONLY here so the runtime image ships no compilers
# (audit DCK-D3: build-essential used to leak into the final image). Base is
# pinned by digest for reproducible builds (audit DCK-D8).
FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6 AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# build-essential covers any sdist-only wheels (e.g. lap) that need a C toolchain.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

# Isolated venv so the runtime stage can copy one self-contained dependency tree.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Pre-install CPU-only torch BEFORE requirements.txt so ultralytics doesn't pull
# the multi-hundred-MB CUDA wheel. Pins live in torch-requirements.txt so CI's
# pip-audit can scan them (audit IS-1).
COPY apps/backend/torch-requirements.txt ./
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
        -r torch-requirements.txt

# Copy only requirements first for better layer caching.
COPY apps/backend/requirements.txt ./
# ultralytics hard-depends on the full opencv-python (GUI build → needs libGL +
# libxcb at runtime). Force the headless build to own the cv2/ files so the
# runtime image needs no X11/GL libs (audit DCK-D2): install the tree, then drop
# BOTH opencv variants and reinstall only headless (pip resolves the dependency
# graph, not file order, so this explicit last-write is the deterministic fix).
# The version is READ FROM requirements.txt (single source of truth) so this
# reinstall can never silently ship a different opencv than the pinned one.
RUN pip install -r requirements.txt \
 && opencv_pin="$(sed -n 's/^opencv-python-headless==//p' requirements.txt)" \
 && pip uninstall -y opencv-python opencv-python-headless \
 && pip install "opencv-python-headless==${opencv_pin}"

# Optional CPU accelerator (OpenVINO, ~+400 MB). OFF by default to keep the local image lean;
# build with `--build-arg INSTALL_ACCEL=true` (compose: BACKEND_INSTALL_ACCEL=true in .env) so
# local CPU inference auto-selects the OpenVINO IR like the cloud image (~1.5x faster at a 2-CPU
# budget). The backend transparently falls back to best.pt when openvino is absent, so leaving
# this off is fully supported — the IR bind-mounted via ./models is simply unused.
ARG INSTALL_ACCEL=false
COPY apps/backend/requirements-accel.txt ./
RUN if [ "$INSTALL_ACCEL" = "true" ]; then pip install -r requirements-accel.txt; fi

# ---- runtime stage --------------------------------------------------------
# Slim final image: no compilers, no GUI libs, no curl, no test tooling.
FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6 AS runtime

# No DATABASE_URL here: baking even the default dev credentials into image ENV
# exposes them to every `docker inspect`/registry scan, and compose always supplies
# the real value. The identical app-level default in config.py covers standalone
# runs (audit IS-8). Likewise FORWARDED_ALLOW_IPS and the runway geometry under
# /app/configs are supplied by compose (env + ./configs:ro bind mount); the supported
# local entrypoint is `docker compose up`, not a bare `docker run` of this image.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PAPI_MODEL_REGISTRY_PATH=/models/serving/models.json \
    PAPI_MODEL_PATH=/models/serving/best.pt \
    PAPI_STORAGE_DIR=/storage

# Never let ultralytics pip-install the full opencv-python at runtime — keeps the
# headless guarantee robust even if an import path changes (audit DCK-RE BACKEND-2).
ENV YOLO_AUTOINSTALL=False

# Runtime-only system libs. opencv-python-headless still needs libglib2.0-0
# (libgthread); the libGL/X11 stack is gone with the headless wheel (audit
# DCK-D2). No curl — the healthcheck uses the Python stdlib (audit DCK-D11).
# NOTE: the base image is digest-pinned and pip deps are version-pinned, but this apt layer is
# the one intentionally NON-reproducible input — pinning an exact libglib2.0-0 version would just
# break on the next Debian mirror rotation, and the lib is ABI-stable, so we accept floating it.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

# The dependency tree, already built in the builder venv.
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app/apps/backend

# Backend source plus the shared PAPI package imported by runtime state and
# detector modules. The repository-root build context is required so both
# trees are available without duplicating shared constants inside the backend.
COPY apps/backend/app ./app
COPY packages/papi/src/papi ./papi

# Non-root runtime user owning the app + storage + model mount points and a
# home dir (ultralytics writes its settings/cache under $HOME on first use)
# (audit DCK-MAJ-3). The model-lifecycle volumes (/user_models, /datasets, /jobs)
# MUST be created + chowned here too: a named volume inherits the ownership of its
# image mountpoint when first created, so without this they mount root-owned and
# the non-root papi user gets EPERM writing uploads / datasets / startup seeds.
RUN groupadd --system papi \
 && useradd --system --gid papi --create-home --shell /usr/sbin/nologin papi \
 && mkdir -p /storage /models /user_models /datasets /jobs \
 && chown -R papi:papi /app /storage /models /user_models /datasets /jobs /home/papi

USER papi

EXPOSE 8000

# Readiness via the stdlib (no curl in the image), matching Dockerfile.cloud + the compose
# override: the bare /health liveness stub would report healthy with the database unreachable or
# the model unloaded, so a standalone `docker run` of this image would look healthy but 500 on the
# first request. /health/ready checks DB + model. start-period covers the model pre-warm + smoke
# inference at startup.
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
