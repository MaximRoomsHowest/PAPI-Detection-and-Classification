# PAPI Python Package

Reusable ML/data code for the project lives here.

| Path | Purpose |
|---|---|
| `src/papi/` | Importable Python package for metadata, geometry, projection, sampling, CVAT export, tracking, and state logic. |
| `tests/` | Pytest coverage for the shared package and generated sequence artifacts. |

Run from the repo root:

```powershell
.venv\Scripts\python.exe -m pytest packages/papi/tests
.venv\Scripts\python.exe -m ruff check packages/papi
```
