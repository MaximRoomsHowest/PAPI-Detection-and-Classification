#!/usr/bin/env bash
set -euo pipefail

AZURE_LOCATION="${AZURE_LOCATION:-francecentral}"
RESOURCE_GROUP="${RESOURCE_GROUP:-rg-papi-vision-demo}"
APP_NAME="${APP_NAME:-papi-vision-demo}"
ACR_NAME="${ACR_NAME:?Set ACR_NAME to a globally unique lowercase registry name.}"
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:?Set STORAGE_ACCOUNT to a globally unique lowercase storage name.}"
POSTGRES_SERVER="${POSTGRES_SERVER:?Set POSTGRES_SERVER to a globally unique PostgreSQL server name.}"
POSTGRES_USER="${POSTGRES_USER:-papiadmin}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD. Use openssl rand -hex 24.}"
BLOB_CONTAINER="${PAPI_BLOB_CONTAINER:-papi-media}"
LOG_WORKSPACE="${LOG_WORKSPACE:-${APP_NAME}-logs}"
CONTAINERAPPS_ENV="${CONTAINERAPPS_ENV:-${APP_NAME}-env}"

REQUIRED_PROVIDERS=(
  Microsoft.App
  Microsoft.ContainerRegistry
  Microsoft.DBforPostgreSQL
  Microsoft.OperationalInsights
  Microsoft.Storage
)

for PROVIDER in "${REQUIRED_PROVIDERS[@]}"; do
  az provider register --namespace "$PROVIDER" --wait
done

if [[ "$(az group exists --name "$RESOURCE_GROUP")" == "true" ]]; then
  EXISTING_LOCATION="$(
    az group show \
      --name "$RESOURCE_GROUP" \
      --query location \
      --output tsv
  )"

  if [[ "$EXISTING_LOCATION" != "$AZURE_LOCATION" ]]; then
    cat >&2 <<EOF
Resource group '$RESOURCE_GROUP' already exists in '$EXISTING_LOCATION'.
Azure resource group locations cannot be changed after creation.

Use a new resource group name:
  export RESOURCE_GROUP=${RESOURCE_GROUP}-${AZURE_LOCATION}

Or delete the existing group if it is safe to remove:
  az group delete --name "$RESOURCE_GROUP"
EOF
    exit 1
  fi
fi

az group create \
  --name "$RESOURCE_GROUP" \
  --location "$AZURE_LOCATION"

if ! az acr show --resource-group "$RESOURCE_GROUP" --name "$ACR_NAME" >/dev/null 2>&1; then
  az acr create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$ACR_NAME" \
    --location "$AZURE_LOCATION" \
    --sku Basic \
    --admin-enabled true
fi

if ! az storage account show --resource-group "$RESOURCE_GROUP" --name "$STORAGE_ACCOUNT" >/dev/null 2>&1; then
  az storage account create \
    --resource-group "$RESOURCE_GROUP" \
    --location "$AZURE_LOCATION" \
    --name "$STORAGE_ACCOUNT" \
    --sku Standard_LRS \
    --kind StorageV2 \
    --allow-blob-public-access false
fi

STORAGE_CONNECTION_STRING="$(
  az storage account show-connection-string \
    --resource-group "$RESOURCE_GROUP" \
    --name "$STORAGE_ACCOUNT" \
    --query connectionString \
    --output tsv
)"

az storage container create \
  --name "$BLOB_CONTAINER" \
  --connection-string "$STORAGE_CONNECTION_STRING" \
  --public-access off

if ! az postgres flexible-server show --resource-group "$RESOURCE_GROUP" --name "$POSTGRES_SERVER" >/dev/null 2>&1; then
  az postgres flexible-server create \
    --resource-group "$RESOURCE_GROUP" \
    --location "$AZURE_LOCATION" \
    --name "$POSTGRES_SERVER" \
    --admin-user "$POSTGRES_USER" \
    --admin-password "$POSTGRES_PASSWORD" \
    --version 16 \
    --tier Burstable \
    --sku-name Standard_B1ms \
    --storage-size 32 \
    --yes
fi

if ! az postgres flexible-server db show \
  --resource-group "$RESOURCE_GROUP" \
  --server-name "$POSTGRES_SERVER" \
  --name papi_backend >/dev/null 2>&1; then
  az postgres flexible-server db create \
    --resource-group "$RESOURCE_GROUP" \
    --server-name "$POSTGRES_SERVER" \
    --name papi_backend
fi

# Demo-friendly Azure access path. Restrict networking before production use.
if ! az postgres flexible-server firewall-rule show \
  --resource-group "$RESOURCE_GROUP" \
  --server-name "$POSTGRES_SERVER" \
  --name allow-azure-services >/dev/null 2>&1; then
  az postgres flexible-server firewall-rule create \
    --resource-group "$RESOURCE_GROUP" \
    --server-name "$POSTGRES_SERVER" \
    --name allow-azure-services \
    --start-ip-address 0.0.0.0 \
    --end-ip-address 0.0.0.0
fi

if ! az monitor log-analytics workspace show \
  --resource-group "$RESOURCE_GROUP" \
  --workspace-name "$LOG_WORKSPACE" >/dev/null 2>&1; then
  az monitor log-analytics workspace create \
    --resource-group "$RESOURCE_GROUP" \
    --workspace-name "$LOG_WORKSPACE" \
    --location "$AZURE_LOCATION"
fi

if ! az containerapp env show --resource-group "$RESOURCE_GROUP" --name "$CONTAINERAPPS_ENV" >/dev/null 2>&1; then
  az containerapp env create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$CONTAINERAPPS_ENV" \
    --location "$AZURE_LOCATION" \
    --logs-workspace-id "$(
      az monitor log-analytics workspace show \
        --resource-group "$RESOURCE_GROUP" \
        --workspace-name "$LOG_WORKSPACE" \
        --query customerId \
        --output tsv
    )" \
    --logs-workspace-key "$(
      az monitor log-analytics workspace get-shared-keys \
        --resource-group "$RESOURCE_GROUP" \
        --workspace-name "$LOG_WORKSPACE" \
        --query primarySharedKey \
        --output tsv
    )"
fi

echo "Azure resources are ready."
echo "Next: bash infra/azure/scripts/build-and-push.sh"
