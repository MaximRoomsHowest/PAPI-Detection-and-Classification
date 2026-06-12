# Azure Deployment

This folder deploys the PAPI Vision demo to Azure Container Apps.

The cloud shape is:

- Azure Container Registry for Docker images.
- Azure Container Apps with two sidecar containers:
  - frontend nginx exposed publicly on port 8080
  - backend FastAPI private on localhost:8000
- Azure Database for PostgreSQL Flexible Server for logs/results/runways.
- Azure Blob Storage for uploaded/annotated media artifacts.

## Prerequisites

Install and sign in:

```bash
az login
az account set --subscription "<your-subscription-id>"
az extension add --name containerapp --upgrade
```

Choose names. ACR and storage names must be globally unique and lowercase:

```bash
export AZURE_LOCATION=francecentral
export RESOURCE_GROUP=rg-papi-vision-demo
export APP_NAME=papi-vision-demo
export ACR_NAME=papivisiondemo$RANDOM
export STORAGE_ACCOUNT=papivisiondemo$RANDOM
export POSTGRES_SERVER=papi-vision-demo-pg-$RANDOM
export POSTGRES_USER=papiadmin
export POSTGRES_PASSWORD="$(openssl rand -hex 24)"
export PAPI_API_KEY="$(openssl rand -hex 32)"
```

Do not commit these values.

## Deploy

From the repository root:

```bash
bash infra/azure/scripts/create-resources.sh
bash infra/azure/scripts/build-and-push.sh
bash infra/azure/scripts/deploy-containerapp.sh
bash infra/azure/scripts/smoke-test.sh
```

The deploy script prints the public site URL at the end.

## Redeploying new code to the EXISTING environment

Skip `create-resources.sh` entirely — only the owner of the original
deployment (whose `az login` can see the resource group) needs to run this.

1. Check out the branch to ship and log in:

   ```bash
   git checkout code-review && git pull
   az login
   ```

2. Re-export the deployment variables. If the original shell is gone, the
   generated names are rediscoverable:

   ```bash
   export RESOURCE_GROUP=rg-papi-vision-demo
   export APP_NAME=papi-vision-demo
   export ACR_NAME=$(az acr list -g "$RESOURCE_GROUP" --query "[0].name" -o tsv)
   export POSTGRES_SERVER=$(az postgres flexible-server list -g "$RESOURCE_GROUP" --query "[0].name" -o tsv)
   export STORAGE_ACCOUNT=$(az storage account list -g "$RESOURCE_GROUP" --query "[0].name" -o tsv)
   ```

3. Two values only you have:
   - `POSTGRES_PASSWORD` must be the **original** one — the database keeps
     its password and the deploy script rewrites the connection-string
     secret from this variable, so a wrong value breaks DB connectivity.
     If it is lost, reset it first:
     `az postgres flexible-server update -g $RESOURCE_GROUP -n $POSTGRES_SERVER --admin-password <new>` —
     then export the new one.
   - `PAPI_API_KEY` may be the original OR a fresh value — the SAME shell
     export feeds both the frontend build (baked into the bundle) and the
     backend secret, so as long as both scripts below run from this shell
     the two sides stay consistent.

4. Build, push, deploy, verify (no local Docker needed with ACR Tasks):

   ```bash
   USE_ACR_TASKS=true bash infra/azure/scripts/build-and-push.sh
   bash infra/azure/scripts/deploy-containerapp.sh
   bash infra/azure/scripts/smoke-test.sh
   ```

   Rebuild **both** images: the sample picker and its assets live in the
   frontend image; the two-minute sample video needs the backend image for
   the raised `PAPI_MAX_VIDEO_SECONDS` default and the `/media` byte-range
   support (video seeking). Custom domains on the app are preserved.

5. Confirm the new build is live (anonymous, no key needed):

   ```bash
   curl -s -o /dev/null -w '%{http_code}\n' https://www.papivision.software/demo-samples/sample-video.json   # 200 = samples shipped
   curl -s -o /dev/null -w '%{http_code}\n' https://www.papivision.software/api/models                        # 401 = new backend (the old build returns 404)
   ```

## Important notes

- The frontend is public. The backend is not exposed directly; nginx proxies `/api`, `/media`, and health checks to the backend sidecar.
- The frontend image ships `nginx.azure.conf.template` (selected via the
  `NGINX_CONF` build arg); like the local image, the body-size cap renders from
  `NGINX_CLIENT_MAX_BODY_SIZE` at container start, no rebuild needed.
- The frontend bundle receives `VITE_PAPI_API_KEY` at build time so it can call the production backend. This is acceptable for a demo but not a true security boundary because browser bundles are public.
- PostgreSQL is configured for a demo-friendly public access path. Tighten networking before any real production deployment.
- Blob Storage is private. Media is streamed through the backend `/media/...` route.
- Use `PAPI_ENV=production` in Azure so the backend refuses to start without a non-default database URL and API key.
- The backend image bakes the whole `models/serving/` slot (weights, registry,
  model card); registry entries pointing at non-baked training paths show up as
  unavailable in the model picker, which is expected.
- Images are tagged `cloud` (moving, what the deploy script references) plus an
  immutable `cloud-<git-sha>` for tracing a running revision back to its commit.

Known trade-offs of the script-based deploy (fine for the demo, revisit for
anything longer-lived):

- `deploy-containerapp.sh` hand-builds the Container App manifest with `jq` and
  passes secrets (database URL, storage connection string, API key) through
  process environment/arguments — they end up stored as Container Apps secrets,
  but a shared CI runner could log them. Azure Key Vault + Bicep/IaC is the
  production-shaped alternative.
- Provisioning is polled with a fixed retry loop rather than `az ... --wait`.

## Cleanup

To delete all demo resources:

```bash
az group delete --name "$RESOURCE_GROUP"
```
