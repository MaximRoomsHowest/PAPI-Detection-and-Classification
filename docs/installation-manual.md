# PAPI Lights Detection and Classification — Installation Manual

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
| Python (for path 2) | 3.10+ (3.12 recommended) | https://www.python.org/downloads/ |
| Node.js (for path 2) | 24.x | https://nodejs.org |
| Disk space | ~ 8 GB | for Docker images + model weights |
| RAM | ≥ 8 GB | inference is CPU-only by default |

## 2. Clone the repository

```bash
git clone https://github.com/MaximRoomsHowest/PAPI-Detection-and-Classification.git
cd PAPI-Detection-and-Classification
# Pin to the v1.0 release if you want the audited cut:
git checkout v1.0
```

## 3. Model weights (already in the repo)

The trained serving checkpoint ships **committed** in the repo at:

```
models/serving/best.pt
```

It is whitelisted in `.gitignore`, so a normal clone already has it
and **no action is required here** — skip to §4.

Only if `models/serving/best.pt` is missing or you deliberately want to
fall back to the untrained base weight, seed the slot from the base
checkpoint. Note this **overwrites the trained checkpoint** with the
untrained base weight, so restore the trained `best.pt` (e.g. via
`git checkout models/serving/best.pt`) before any demo:

```powershell
# Windows PowerShell — explicit base-weight fallback only
Copy-Item models\base\yolo26s.pt models\serving\best.pt -Force
```

```bash
# Linux / macOS / Git Bash — explicit base-weight fallback only
cp models/base/yolo26s.pt models/serving/best.pt
```

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
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
pip install -r apps\backend\requirements-dev.txt

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
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pip install -r apps/backend/requirements-dev.txt
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

1. **Generate a strong API key** and set it — together with the
   production flag — in `.env`:
   ```bash
   PAPI_API_KEY=$(openssl rand -base64 32)
   echo "PAPI_API_KEY=$PAPI_API_KEY" >> .env
   echo "PAPI_ENV=production" >> .env
   ```
   The backend will refuse to start without a key when
   `PAPI_ENV=production` (audit B-CRIT-5). It will also refuse to
   start with the default `papi:papi@localhost` database credentials
   in production mode, so make sure `PAPI_DATABASE_URL` points at a
   real database with rotated credentials.
2. **Rotate the Postgres password** in `.env`. Both
   `POSTGRES_PASSWORD` and `PAPI_DATABASE_URL` must agree on the new
   value.
3. **Set `FRONTEND_PAPI_API_URL`** to the public hostname the
   browser will resolve.
4. **Run behind a reverse proxy** that terminates TLS — see
   §7.1 below for a concrete Caddy recipe. Neither the nginx
   shipped inside `apps/frontend/Dockerfile` nor uvicorn is
   configured for HTTPS by itself.
5. **Restrict the backend port**. Remove the host port mapping
   for backend `:8000` and let only the reverse proxy reach it.

### 7.0 Azure Container Apps (scripted, what powers the public demo)

The repository ships a complete Azure deployment under `infra/azure/`
(scripts + README): Container Registry, a Container App running the
frontend nginx and backend as sidecars, PostgreSQL Flexible Server, and
Azure Blob Storage for media artifacts. The public demo at
`https://www.papivision.software` runs this path.

Storage backend selection is environment-driven and defaults to the
local filesystem — the Azure deployment sets:

| Variable | Value | Purpose |
| --- | --- | --- |
| `PAPI_STORAGE_BACKEND` | `azure_blob` (default `local`) | Media artifacts go to Blob Storage instead of `PAPI_STORAGE_DIR`; `/media/...` URLs keep working (the backend proxies, with byte-range support for video seeking). |
| `PAPI_BLOB_CONTAINER` | container name (default `papi-media`) | Blob container for `uploads/` and `exports/`. |
| `AZURE_STORAGE_CONNECTION_STRING` | secret | Simplest auth for the first deploy. |
| `AZURE_STORAGE_ACCOUNT_URL` | account URL | Alternative: managed identity (`DefaultAzureCredential`) instead of a connection string. |

Follow `infra/azure/README.md` for the end-to-end recipe
(`create-resources.sh` → `build-and-push.sh` → `deploy-containerapp.sh`
→ `smoke-test.sh`). Local compose ignores all of this and keeps
filesystem storage.

### 7.1 HTTPS termination — Caddy recipe (recommended)

Caddy is the lowest-effort way to get a Let's Encrypt certificate
in front of the stack. Single binary, automatic HTTPS, automatic
renewal, no separate certbot cron.

Add a fourth service to `compose.yaml` (or a
`compose.prod.yaml` override) and remove the host ports from
the backend + frontend services so only Caddy can reach them:

```yaml
services:
  caddy:
    image: caddy:2-alpine
    container_name: papi-caddy
    restart: unless-stopped
    ports:
      - "80:80"      # ACME HTTP-01 challenge + redirect to 443
      - "443:443"    # the actual TLS endpoint
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data            # certificate + key storage
      - caddy_config:/config
    depends_on:
      - backend
      - frontend

volumes:
  caddy_data:
  caddy_config:
```

A minimal `Caddyfile` at the repo root:

```caddyfile
papi.example.com {
    # The frontend bundle (Vite/React/Nginx unprivileged container).
    handle_path /api/* {
        # Strip the /api prefix and forward to the backend.
        rewrite * /api{path}
        reverse_proxy backend:8000
    }
    handle_path /media/* {
        rewrite * /media{path}
        reverse_proxy backend:8000
    }
    # Everything else: the SPA.
    reverse_proxy frontend:8080

    # Security headers — supplement what the nginx container already
    # adds. Defence-in-depth, not duplication: Caddy can override or
    # extend each header before the browser sees the response.
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
    }
}
```

Replace `papi.example.com` with the real hostname; Caddy fetches
the certificate from Let's Encrypt automatically on first start
and renews it ~30 days before expiry. No further configuration
needed.

Verification after bringing up the new stack:

```bash
docker compose -f compose.yaml -f compose.prod.yaml up -d --build
curl -fsSI https://papi.example.com/
# Expected: HTTP/2 200 + Strict-Transport-Security header
curl -fsS https://papi.example.com/api/runways
# Expected: 401 (no X-API-Key header), proving the API is gated end-to-end
```

### 7.2 Alternatives

If your operations team standardises on a different reverse
proxy, the same shape works:

| Proxy | When it fits | Setup hint |
|---|---|---|
| **Traefik** | You already have a Docker Swarm / Kubernetes platform with Traefik in front of everything | Add the same routing rules as labels on the backend + frontend services |
| **nginx + certbot** | You have a hardened nginx baseline already | Point `proxy_pass` at `backend:8000` and `frontend:8080`; run `certbot --nginx -d papi.example.com` once |
| **AWS ALB / Cloudflare / Fastly** | The deployment lives in a managed cloud or behind a CDN | Point the load balancer at the host's backend + frontend ports; let the cloud handle TLS |

For any choice, two operational rules hold:

1. **Terminate TLS at the proxy, not at uvicorn.** Uvicorn can serve
   HTTPS but its certificate handling is bare-bones; managed
   reverse proxies do auto-renewal, OCSP stapling, and HSTS for you.
2. **Strip the host-machine port mappings on `backend:8000` and
   `frontend:8080`.** With Caddy / Traefik as the only ingress
   path, the analyze endpoints become unreachable from the public
   internet except via TLS.

## 8. Verification checklist

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
