# PAPI Vision — Installation Manual

How to install and run the PAPI Detection & Classification system
from a fresh machine. Two supported paths:

1. **Docker compose** — recommended for demos and reviewers.
2. **Native development** — for the team's day-to-day work.

> **Already installed?** See [user-manual.md](user-manual.md)
> for usage.

## 1. Prerequisites

| Requirement | Version | Where to get it |
| --- | --- | --- |
| Git | any recent | https://git-scm.com |
| Docker Desktop (for path 1) | 4.30+ | https://www.docker.com/products/docker-desktop |
| Python (for path 2) | 3.10+ | https://www.python.org/downloads/ |
| Node.js (for path 2) | 20.x | https://nodejs.org |
| Disk space | ~ 8 GB | for Docker images + model weights |
| RAM | ≥ 8 GB | inference is CPU-only by default |

## 2. Clone the repository

```bash
git clone https://github.com/MaximRoomsHowest/PAPI-Detection-and-Classification.git
cd PAPI-Detection-and-Classification
# Pin to the v1.0 release if you want the audited cut:
git checkout v1.0
```

## 3. Provide the model weights

The model file is not in the repo. Drop a trained checkpoint at:

```
models/serving/best.pt
```

If you only want to smoke-test the API, copy the base weights into
the serving slot:

```powershell
# Windows PowerShell
Copy-Item models\base\yolo26n.pt models\serving\best.pt -Force
```

```bash
# Linux / macOS / Git Bash
cp models/base/yolo26n.pt models/serving/best.pt
```

The trained PAPI checkpoint should replace this file before any
demo.

## 4. Path 1 — Docker compose (recommended)

This brings up Postgres + the FastAPI backend + the Nginx-served
React frontend, all behind one command.

```bash
# Step 1 — create your environment file
cp .env.example .env
# Edit .env: at minimum, change POSTGRES_PASSWORD to a non-default value.
# Leave PAPI_ENV=local for development; switch to PAPI_ENV=production for
# a real deployment (will require PAPI_API_KEY to be set).

# Step 2 — build the images and start the stack
docker compose up -d --build

# Step 3 — verify everything is up
docker ps --filter "name=papi-"
# All three of papi-postgres, papi-backend, papi-frontend should show
# "Up (healthy)" within ~30 seconds.

# Step 4 — open the app
# Visit http://localhost:5173 in your browser.
```

To stop the stack:

```bash
docker compose down
# Add -v to also drop the named volumes (loses logs + uploads):
docker compose down -v
```

### Verifying the install

```bash
curl -fsS http://localhost:8000/health
# Expected: {"status":"ok"}

curl -fsS http://localhost:8000/api/runways
# Expected: a JSON list with PAPI 06 and PAPI 24 entries.

# Frontend is reachable at http://localhost:5173/
# Live demo at http://localhost:5173/live-demo
```

### Updating model weights without rebuilding

Because `models/` is bind-mounted into the backend container,
replacing `models/serving/best.pt` on the host and restarting only
the backend swaps the model with no rebuild:

```bash
docker compose restart backend
```

## 5. Path 2 — Native development

Use this when iterating on backend / frontend code.

### 5.1 Backend (FastAPI)

```powershell
# Windows PowerShell from the repo root
py -3.10 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
pip install -r apps\backend\requirements.txt

# Postgres is still needed — easiest to keep using docker for it:
docker compose up -d postgres

# Create the backend env file:
Copy-Item apps\backend\.env.example apps\backend\.env
# Edit the file if your postgres credentials differ from the defaults.

# Run the backend:
cd apps\backend
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

```bash
# Linux / macOS equivalents
python3.10 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pip install -r apps/backend/requirements.txt
docker compose up -d postgres
cp apps/backend/.env.example apps/backend/.env
cd apps/backend
python -m uvicorn app.main:app --reload --port 8000
```

The backend is now serving at `http://127.0.0.1:8000`. Interactive
API docs at `http://127.0.0.1:8000/docs`.

### 5.2 Frontend (Vite + React)

In a separate terminal:

```bash
cd apps/frontend
cp .env.example .env       # or "copy" on Windows
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Vite hot-reloads on every code change. The dev server proxies API
calls based on the `VITE_PAPI_API_URL` in `apps/frontend/.env`.

## 6. Running the data pipeline (optional)

The ML pipeline lives at `workflows/scripts/pipeline.py` and is
**not** required to use the application — it's how the team
generates training data.

```bash
# Activate the same .venv as the backend native path

# Create a junction from data/raw/ to the archived dataset
# (Windows-specific — adjust path for the actual artifact location):
cmd /c mklink /J data\raw ..\PAPI-artifacts\2026-05-26-cleanup\PROJECT1-PAPI

# Run all five pipeline stages in order:
python workflows/scripts/pipeline.py all

# Or pick a single stage:
python workflows/scripts/pipeline.py extract --limit 100
```

## 7. Production deployment notes

For a real deployment (not a local demo):

1. **Generate a strong API key** and set it in `.env`:
   ```bash
   PAPI_API_KEY=$(openssl rand -base64 32)
   echo "PAPI_API_KEY=$PAPI_API_KEY" >> .env
   PAPI_ENV=production
   ```
   The backend will refuse to start without a key when
   `PAPI_ENV=production` (audit B-CRIT-5).
2. **Rotate the Postgres password** in `.env`.
3. **Set `FRONTEND_PAPI_API_URL`** to the public hostname the
   browser will resolve.
4. **Run behind a reverse proxy** (Caddy, Traefik) that terminates
   TLS — neither nginx in this repo nor uvicorn is configured for
   HTTPS by itself.
5. **Restrict the backend port**. Remove the host port mapping
   for backend `:8000` and let only the reverse proxy reach it.

## 8. Verification checklist (for graders / reviewers)

After installation, the following should all succeed without error:

```bash
# In a venv where the project is installed editable:
pytest packages/papi/tests
pytest apps/backend/tests
ruff check apps/backend packages/papi workflows/scripts

# In apps/frontend with deps installed:
npm run lint
npm run build

# With docker compose up:
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/api/runways
curl -fsI http://localhost:5173/   # 200 OK
```

The GitHub Actions CI workflow (`.github/workflows/ci.yml`) runs
this exact set on every push.

## 9. Uninstalling

```bash
# Tear down containers + named volumes:
docker compose down -v

# Remove built images:
docker rmi papi-detection-and-classification-backend
docker rmi papi-detection-and-classification-frontend

# Delete the venv (native install only):
rm -rf .venv     # Linux/macOS
Remove-Item -Recurse -Force .venv   # Windows PowerShell
```

Everything else under the repo is plain files — `rm -rf` the clone
directory if you want to remove the project entirely.

## 10. Where to ask for help

- [GitHub Issues](https://github.com/MaximRoomsHowest/PAPI-Detection-and-Classification/issues) — bug reports + feature requests.
- The team's BigBrain hub at `03-projects/intersoft-papi-detection`
  for design rationale and meeting decisions.
- The audit doc `03-projects/papi-codebase-audit-2026-05-27` for
  known issues and their current status.
