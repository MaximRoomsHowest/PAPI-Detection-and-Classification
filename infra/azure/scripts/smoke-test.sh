#!/usr/bin/env bash
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-rg-papi-vision-demo}"
APP_NAME="${APP_NAME:-papi-vision-demo}"

APP_URL="https://$(az containerapp show --resource-group "$RESOURCE_GROUP" --name "$APP_NAME" --query properties.configuration.ingress.fqdn --output tsv)"

echo "Testing $APP_URL"
curl -fsS "$APP_URL/health" >/dev/null
curl -fsS "$APP_URL/health/ready" >/dev/null

echo "Smoke test passed:"
echo "$APP_URL"
