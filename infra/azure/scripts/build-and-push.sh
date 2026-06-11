#!/usr/bin/env bash
set -euo pipefail

ACR_NAME="${ACR_NAME:?Set ACR_NAME.}"
PAPI_API_KEY="${PAPI_API_KEY:?Set PAPI_API_KEY before building the frontend.}"
BACKEND_IMAGE_NAME="${BACKEND_IMAGE_NAME:-papi-backend:cloud}"
FRONTEND_IMAGE_NAME="${FRONTEND_IMAGE_NAME:-papi-frontend:cloud}"
USE_ACR_TASKS="${USE_ACR_TASKS:-false}"
DOCKER_PLATFORM="${DOCKER_PLATFORM:-linux/amd64}"

if [[ "$USE_ACR_TASKS" == "true" ]]; then
  az acr build \
    --registry "$ACR_NAME" \
    --image "$BACKEND_IMAGE_NAME" \
    --file apps/backend/Dockerfile.cloud \
    .

  az acr build \
    --registry "$ACR_NAME" \
    --image "$FRONTEND_IMAGE_NAME" \
    --file apps/frontend/Dockerfile \
    --build-arg VITE_PAPI_API_URL= \
    --build-arg VITE_PAPI_API_KEY="$PAPI_API_KEY" \
    --build-arg NGINX_CONF=nginx.azure.conf \
    apps/frontend
else
  ACR_LOGIN_SERVER="$(az acr show --name "$ACR_NAME" --query loginServer --output tsv)"

  az acr login --name "$ACR_NAME"

  docker build \
    --platform "$DOCKER_PLATFORM" \
    --file apps/backend/Dockerfile.cloud \
    --tag "${ACR_LOGIN_SERVER}/${BACKEND_IMAGE_NAME}" \
    .
  docker push "${ACR_LOGIN_SERVER}/${BACKEND_IMAGE_NAME}"

  docker build \
    --platform "$DOCKER_PLATFORM" \
    --file apps/frontend/Dockerfile \
    --build-arg VITE_PAPI_API_URL= \
    --build-arg VITE_PAPI_API_KEY="$PAPI_API_KEY" \
    --build-arg NGINX_CONF=nginx.azure.conf \
    --tag "${ACR_LOGIN_SERVER}/${FRONTEND_IMAGE_NAME}" \
    apps/frontend
  docker push "${ACR_LOGIN_SERVER}/${FRONTEND_IMAGE_NAME}"
fi

echo "Images pushed to Azure Container Registry."
echo "Next: bash infra/azure/scripts/deploy-containerapp.sh"
