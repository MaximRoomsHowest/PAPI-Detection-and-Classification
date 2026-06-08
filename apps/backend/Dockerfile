# syntax=docker/dockerfile:1.7

# ---- builder stage --------------------------------------------------------
# Compiles/installs the Python dependency tree into a self-contained venv.
# build-essential lives ONLY here so the runtime image ships no compilers
# (audit DCK-D3: build-essential used to leak into the final image). Base is
# pinned by digest for reproducible builds (audit DCK-D8).
FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203 AS builder

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
# the multi-hundred-MB CUDA wheel.
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
        torch==2.5.1 torchvision==0.20.1

# Copy only requirements first for better layer caching.
COPY requirements.txt ./
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

# ---- runtime stage --------------------------------------------------------
# Slim final image: no compilers, no GUI libs, no curl, no test tooling.
FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PAPI_MODEL_PATH=/models/serving/best.pt \
    PAPI_STORAGE_DIR=/storage \
    DATABASE_URL=postgresql+psycopg://papi:papi@postgres:5432/papi_backend

# Never let ultralytics pip-install the full opencv-python at runtime — keeps the
# headless guarantee robust even if an import path changes (audit DCK-RE BACKEND-2).
ENV YOLO_AUTOINSTALL=False

# Runtime-only system libs. opencv-python-headless still needs libglib2.0-0
# (libgthread); the libGL/X11 stack is gone with the headless wheel (audit
# DCK-D2). No curl — the healthcheck uses the Python stdlib (audit DCK-D11).
RUN apt-get update \
 && apt-get install -y --no-install-recommends libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

# The dependency tree, already built in the builder venv.
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app/apps/backend

# Backend source.
COPY app ./app

# Non-root runtime user owning the app + storage + model mount points and a
# home dir (ultralytics writes its settings/cache under $HOME on first use)
# (audit DCK-MAJ-3).
RUN groupadd --system papi \
 && useradd --system --gid papi --create-home --shell /usr/sbin/nologin papi \
 && mkdir -p /storage /models \
 && chown -R papi:papi /app /storage /models /home/papi

USER papi

EXPOSE 8000

# Liveness via the stdlib (no curl in the image). start-period covers the model
# pre-warm + smoke inference at startup.
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
