#!/usr/bin/env bash
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-rg-papi-vision-demo}"
APP_NAME="${APP_NAME:-papi-vision-demo}"
ACR_NAME="${ACR_NAME:?Set ACR_NAME.}"
POSTGRES_SERVER="${POSTGRES_SERVER:?Set POSTGRES_SERVER.}"
POSTGRES_USER="${POSTGRES_USER:-papiadmin}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD.}"
PAPI_API_KEY="${PAPI_API_KEY:?Set PAPI_API_KEY.}"
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:?Set STORAGE_ACCOUNT.}"
BLOB_CONTAINER="${PAPI_BLOB_CONTAINER:-papi-media}"
CONTAINERAPPS_ENV="${CONTAINERAPPS_ENV:-${APP_NAME}-env}"
BACKEND_TAG="${BACKEND_TAG:-cloud}"
FRONTEND_TAG="${FRONTEND_TAG:-cloud}"

ACR_LOGIN_SERVER="$(az acr show --resource-group "$RESOURCE_GROUP" --name "$ACR_NAME" --query loginServer --output tsv)"
ACR_USERNAME="$(az acr credential show --name "$ACR_NAME" --query username --output tsv)"
ACR_PASSWORD="$(az acr credential show --name "$ACR_NAME" --query 'passwords[0].value' --output tsv)"
POSTGRES_FQDN="$(az postgres flexible-server show --resource-group "$RESOURCE_GROUP" --name "$POSTGRES_SERVER" --query fullyQualifiedDomainName --output tsv)"
STORAGE_CONNECTION_STRING="$(az storage account show-connection-string --resource-group "$RESOURCE_GROUP" --name "$STORAGE_ACCOUNT" --query connectionString --output tsv)"
ENVIRONMENT_ID="$(az containerapp env show --resource-group "$RESOURCE_GROUP" --name "$CONTAINERAPPS_ENV" --query id --output tsv)"
SUBSCRIPTION_ID="$(az account show --query id --output tsv)"
RESOURCE_ID="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.App/containerApps/${APP_NAME}"
API_VERSION="${CONTAINERAPP_API_VERSION:-2025-01-01}"

DATABASE_URL="postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_FQDN}:5432/papi_backend?sslmode=require"
BACKEND_IMAGE="${ACR_LOGIN_SERVER}/papi-backend:${BACKEND_TAG}"
FRONTEND_IMAGE="${ACR_LOGIN_SERVER}/papi-frontend:${FRONTEND_TAG}"
DEPLOY_JSON="$(mktemp)"
trap 'rm -f "$DEPLOY_JSON"' EXIT

jq -n \
  --arg location "$(az group show --name "$RESOURCE_GROUP" --query location --output tsv)" \
  --arg environment_id "$ENVIRONMENT_ID" \
  --arg acr_login_server "$ACR_LOGIN_SERVER" \
  --arg acr_username "$ACR_USERNAME" \
  --arg acr_password "$ACR_PASSWORD" \
  --arg database_url "$DATABASE_URL" \
  --arg papi_api_key "$PAPI_API_KEY" \
  --arg storage_connection_string "$STORAGE_CONNECTION_STRING" \
  --arg frontend_image "$FRONTEND_IMAGE" \
  --arg backend_image "$BACKEND_IMAGE" \
  --arg blob_container "$BLOB_CONTAINER" \
  '{
    location: $location,
    properties: {
      managedEnvironmentId: $environment_id,
      configuration: {
        activeRevisionsMode: "Single",
        ingress: {
          external: true,
          targetPort: 8080,
          transport: "Auto"
        },
        registries: [
          {
            server: $acr_login_server,
            username: $acr_username,
            passwordSecretRef: "acr-password"
          }
        ],
        secrets: [
          {name: "acr-password", value: $acr_password},
          {name: "database-url", value: $database_url},
          {name: "papi-api-key", value: $papi_api_key},
          {name: "azure-storage-connection-string", value: $storage_connection_string}
        ]
      },
      template: {
        containers: [
          {
            name: "frontend",
            image: $frontend_image,
            resources: {
              cpu: 0.5,
              memory: "1Gi"
            }
          },
          {
            name: "backend",
            image: $backend_image,
            env: [
              {name: "DATABASE_URL", secretRef: "database-url"},
              {name: "PAPI_ENV", value: "production"},
              {name: "PAPI_API_KEY", secretRef: "papi-api-key"},
              {name: "PAPI_MODEL_PATH", value: "/models/serving/best.pt"},
              {name: "PAPI_STORAGE_DIR", value: "/storage"},
              {name: "PAPI_STORAGE_BACKEND", value: "azure_blob"},
              {name: "PAPI_BLOB_CONTAINER", value: $blob_container},
              {name: "AZURE_STORAGE_CONNECTION_STRING", secretRef: "azure-storage-connection-string"},
              {name: "PAPI_DEVICE", value: "cpu"},
              {name: "PAPI_CONFIDENCE_THRESHOLD", value: "0.4"},
              {name: "PAPI_MAX_UPLOAD_MB", value: "100"},
              {name: "PAPI_MAX_BATCH_UPLOAD_MB", value: "400"},
              {name: "PAPI_MAX_BATCH_FRAMES", value: "200"}
            ],
            resources: {
              cpu: 2.0,
              memory: "4Gi"
            }
          }
        ]
      }
    }
  }' > "$DEPLOY_JSON"

az rest \
  --method put \
  --uri "https://management.azure.com${RESOURCE_ID}?api-version=${API_VERSION}" \
  --body "@${DEPLOY_JSON}" \
  --output none

for _ in {1..60}; do
  PROVISIONING_STATE="$(
    az containerapp show \
      --resource-group "$RESOURCE_GROUP" \
      --name "$APP_NAME" \
      --query properties.provisioningState \
      --output tsv 2>/dev/null || true
  )"

  if [[ "$PROVISIONING_STATE" == "Succeeded" ]]; then
    break
  fi

  if [[ "$PROVISIONING_STATE" == "Failed" ]]; then
    echo "Container App provisioning failed." >&2
    exit 1
  fi

  sleep 10
done

if [[ "$PROVISIONING_STATE" != "Succeeded" ]]; then
  echo "Timed out waiting for Container App provisioning. Last state: ${PROVISIONING_STATE:-unknown}" >&2
  exit 1
fi

APP_URL="https://$(az containerapp show --resource-group "$RESOURCE_GROUP" --name "$APP_NAME" --query properties.configuration.ingress.fqdn --output tsv)"

echo "Container App deployed:"
echo "$APP_URL"
echo "Next: bash infra/azure/scripts/smoke-test.sh"
