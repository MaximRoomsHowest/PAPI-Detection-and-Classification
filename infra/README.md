# Infrastructure

Deployment tooling that lives outside the application image.

| Path | Purpose |
|---|---|
| [`azure/`](azure/) | Optional Azure Container Apps deployment: provisioning, image build/push, deploy, and a smoke test. See [`azure/README.md`](azure/README.md) for prerequisites and the end-to-end flow. |

For local / single-host deployment you do **not** need anything here — use the
root [`compose.yaml`](../compose.yaml) and the
[installation manual](../docs/installation-manual.md). The Azure scripts are a
reference path for a managed cloud deployment.
