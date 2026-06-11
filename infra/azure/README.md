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

## Important notes

- The frontend is public. The backend is not exposed directly; nginx proxies `/api`, `/media`, and health checks to the backend sidecar.
- The frontend bundle receives `VITE_PAPI_API_KEY` at build time so it can call the production backend. This is acceptable for a demo but not a true security boundary because browser bundles are public.
- PostgreSQL is configured for a demo-friendly public access path. Tighten networking before any real production deployment.
- Blob Storage is private. Media is streamed through the backend `/media/...` route.
- Use `PAPI_ENV=production` in Azure so the backend refuses to start without a non-default database URL and API key.

## Cleanup

To delete all demo resources:

```bash
az group delete --name "$RESOURCE_GROUP"
```
