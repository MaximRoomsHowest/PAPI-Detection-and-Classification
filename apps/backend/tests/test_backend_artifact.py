"""InferenceService._resolve_backend_artifact: device-aware backend selection.

The guarantee under test is hardware portability — every host loads its best artifact
and nothing regresses: CPU prefers an optimized sibling (OpenVINO IR > .onnx) at parity
accuracy, CUDA always keeps native .pt, and a missing/forced-absent artifact falls back
to .pt so unusual hosts and uploaded custom models still serve.
"""

import json

from app.config import Settings
from app.services.inference.service import InferenceService
from app.services.model_registry import ModelRegistryEntry


def _service(tmp_path, *, device="cpu", backend="auto"):
    serving = tmp_path / "models" / "serving"
    serving.mkdir(parents=True)
    (serving / "best.pt").write_bytes(b"pt")
    registry_path = serving / "models.json"
    registry_path.write_text(
        json.dumps(
            {
                "default_model_id": "small",
                "models": [
                    {
                        "id": "small",
                        "role": "detector",
                        "path": "models/serving/best.pt",
                        "class_count": 2,
                        "default": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(
        storage_dir=tmp_path / "storage",
        model_path=serving / "best.pt",
        model_registry_path=registry_path,
        device=device,
        inference_backend=backend,
    )
    return InferenceService(settings), serving


def _entry(serving):
    return ModelRegistryEntry(
        id="small", label="x", role="detector", path=serving / "best.pt", class_count=2, default=True
    )


def test_cpu_auto_ignores_onnx_sibling(tmp_path):
    # fp32 ONNX is slower than torch on CPU, so auto must NOT pick an .onnx sibling — only .pt
    # (or an OpenVINO IR). This guards the audit footgun where non-serving models with a
    # committed best.onnx were silently routed to the rejected-slow backend.
    service, serving = _service(tmp_path)
    (serving / "best.onnx").write_bytes(b"onnx")
    assert service._resolve_backend_artifact(_entry(serving)) == serving / "best.pt"


def test_cpu_backend_onnx_forced_picks_onnx_sibling(tmp_path):
    # ONNX is opt-in only: PAPI_INFERENCE_BACKEND=onnx explicitly selects the sibling.
    service, serving = _service(tmp_path, backend="onnx")
    (serving / "best.onnx").write_bytes(b"onnx")
    assert service._resolve_backend_artifact(_entry(serving)) == serving / "best.onnx"


def test_cpu_auto_without_sibling_uses_pt(tmp_path):
    service, serving = _service(tmp_path)
    assert service._resolve_backend_artifact(_entry(serving)) == serving / "best.pt"


def test_cpu_backend_pt_ignores_onnx_sibling(tmp_path):
    service, serving = _service(tmp_path, backend="pt")
    (serving / "best.onnx").write_bytes(b"onnx")
    assert service._resolve_backend_artifact(_entry(serving)) == serving / "best.pt"


def test_cuda_never_routes_to_onnx(tmp_path):
    # The dev-laptop GPU path: native .pt must win even when an ONNX sibling exists.
    service, serving = _service(tmp_path, device="cuda")
    (serving / "best.onnx").write_bytes(b"onnx")
    assert service._resolve_backend_artifact(_entry(serving)) == serving / "best.pt"


def test_cpu_auto_prefers_openvino_over_onnx(tmp_path):
    service, serving = _service(tmp_path)
    (serving / "best.onnx").write_bytes(b"onnx")
    ov = serving / "best_openvino_model"
    ov.mkdir()
    assert service._resolve_backend_artifact(_entry(serving)) == ov


def test_backend_onnx_without_artifact_falls_back_to_pt(tmp_path):
    service, serving = _service(tmp_path, backend="onnx")
    assert service._resolve_backend_artifact(_entry(serving)) == serving / "best.pt"


def test_non_pt_entry_is_taken_verbatim(tmp_path):
    # An entry that already points at .onnx (e.g. an uploaded ONNX) is not "upgraded".
    service, serving = _service(tmp_path)
    onnx_entry = ModelRegistryEntry(
        id="up", label="x", role="detector", path=serving / "custom.onnx", class_count=2
    )
    assert service._resolve_backend_artifact(onnx_entry) == serving / "custom.onnx"


# --- PAPI_DEVICE guard (audit: cuda requested on a CPU-only image must not 500 every request) ---


def test_wants_cuda_detection():
    assert InferenceService._wants_cuda("cuda")
    assert InferenceService._wants_cuda("cuda:1")
    assert InferenceService._wants_cuda("0")  # bare GPU index
    assert not InferenceService._wants_cuda("cpu")


def test_explicit_cuda_without_gpu_falls_back_to_cpu(tmp_path, monkeypatch):
    service, _ = _service(tmp_path, device="cuda")
    monkeypatch.setattr(InferenceService, "_cuda_available", staticmethod(lambda: False))
    assert service.device == "cpu"


def test_explicit_cuda_with_gpu_is_kept(tmp_path, monkeypatch):
    service, _ = _service(tmp_path, device="cuda")
    monkeypatch.setattr(InferenceService, "_cuda_available", staticmethod(lambda: True))
    assert service.device == "cuda"


def test_explicit_cpu_is_used_verbatim(tmp_path):
    service, _ = _service(tmp_path, device="cpu")
    assert service.device == "cpu"
