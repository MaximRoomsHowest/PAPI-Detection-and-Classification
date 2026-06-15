"""Black-box end-to-end user test against a RUNNING backend.

Drives the real HTTP API the way the frontend does and verifies each result against
an explicit expected outcome (PASS/FAIL). Covers: health/readiness, public vs
admin-gated reads, the seeded built-in eval datasets, the protect-from-delete and
protect-from-train guards, a real image + video analysis (to populate logs), the
image/video latency split in /api/stats, an end-to-end evaluate job (real YOLO val
on a built-in set, polled to completion + metric write-back), and promote/disable.

Usage (start a server first, e.g.)::

    $env:PAPI_DATABASE_URL = "sqlite:///<abs>/e2e_test.db"
    $env:PAPI_API_KEY = "e2e-key"; $env:PAPI_RATE_LIMIT_ENABLED = "false"
    .venv/Scripts/python -m uvicorn app.main:app --port 8099   # from apps/backend on PYTHONPATH

    .venv/Scripts/python workflows/scripts/e2e_user_test.py --base http://127.0.0.1:8099 --key e2e-key
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
IMAGE_SAMPLE = next(
    (REPO_ROOT / "data" / "eval" / "builtin-detector-redwhite" / "images").glob("*.jpg"), None
)
VIDEO_SAMPLE = REPO_ROOT / "apps" / "frontend" / "public" / "demo-samples" / "papi24-angle-sweep.mp4"

_results: list[tuple[bool, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _results.append((ok, name, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""), flush=True)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8099")
    ap.add_argument("--key", default="e2e-key")
    args = ap.parse_args()
    base, key = args.base.rstrip("/"), args.key
    admin = {"X-API-Key": key}

    # 1. Readiness
    r = requests.get(f"{base}/health/ready", timeout=30)
    check("health/ready is 200", r.status_code == 200, f"got {r.status_code}: {r.text[:120]}")

    # 2. Default model read (API is gated whenever PAPI_API_KEY is configured — the
    #    public read-only demo is the NO-key deployment; here a key is set, so a key
    #    is required and the no-key call must 401).
    r = requests.get(f"{base}/api/model", timeout=30)
    check("GET /api/model without key is 401 (gated when key set)", r.status_code == 401, f"got {r.status_code}")
    r = requests.get(f"{base}/api/model", headers=admin, timeout=30)
    check("GET /api/model with key 200 + has default id", r.status_code == 200 and bool(r.json().get("model_id")),
          f"{r.status_code} id={r.json().get('model_id') if r.ok else '?'}")

    # 3. Admin gate enforced
    r = requests.get(f"{base}/api/models", timeout=30)
    check("GET /api/models without key is 401", r.status_code == 401, f"got {r.status_code}")

    # 4. Admin model list
    r = requests.get(f"{base}/api/models", headers=admin, timeout=30)
    models = r.json() if r.ok else []
    ids = {m["model_id"] for m in models}
    check("GET /api/models with key lists >=3 models", r.status_code == 200 and len(models) >= 3, f"ids={sorted(ids)}")
    by_id = {m["model_id"]: m for m in models}

    # 5. Built-in datasets seeded, per-role
    r = requests.get(f"{base}/api/datasets", headers=admin, timeout=30)
    ds = {d["id"]: d for d in (r.json() if r.ok else [])}
    det = ds.get("builtin-detector-redwhite", {})
    tr = ds.get("builtin-transition-3class", {})
    check("built-in detector eval set seeded (2-class, ready, n_test=18)",
          det.get("source") == "builtin" and det.get("status") == "ready"
          and len(det.get("class_names") or {}) == 2 and det.get("n_test") == 18,
          f"{det}")
    check("built-in transition eval set seeded (3-class, ready, n_test=24)",
          tr.get("source") == "builtin" and tr.get("status") == "ready"
          and len(tr.get("class_names") or {}) == 3 and tr.get("n_test") == 24,
          f"{tr}")

    # 6. Built-in dataset is delete-protected
    r = requests.delete(f"{base}/api/datasets/builtin-detector-redwhite", headers=admin, timeout=30)
    check("DELETE built-in dataset is refused (400)", r.status_code == 400, f"got {r.status_code}: {r.text[:120]}")

    # 7. Built-in dataset cannot be used for training
    r = requests.post(f"{base}/api/training/prepare", headers=admin,
                      json={"dataset_id": "builtin-detector-redwhite", "base_model_id": None,
                            "hyperparams": {"epochs": 1, "imgsz": 640, "batch": 2, "oversample": 4}}, timeout=60)
    check("prepare-training on a built-in dataset is refused (400)", r.status_code == 400, f"got {r.status_code}: {r.text[:140]}")

    # 8. Real image analysis (populates an image log)
    if IMAGE_SAMPLE and IMAGE_SAMPLE.is_file():
        with IMAGE_SAMPLE.open("rb") as fh:
            r = requests.post(f"{base}/api/analyze", headers=admin,
                              files={"file": (IMAGE_SAMPLE.name, fh, "image/jpeg")}, timeout=180)
        body = r.json() if r.ok else {}
        check("image analysis 200 (media_type=image, has global_state)",
              r.status_code == 200 and body.get("media_type") == "image" and bool(body.get("global_state")),
              f"{r.status_code} state={body.get('global_state')} ms={body.get('processing_ms')}")
    else:
        check("image sample present", False, f"missing {IMAGE_SAMPLE}")

    # 9. Real video analysis (populates a video log) — slower
    if VIDEO_SAMPLE.is_file():
        with VIDEO_SAMPLE.open("rb") as fh:
            r = requests.post(f"{base}/api/analyze", headers=admin,
                              files={"file": (VIDEO_SAMPLE.name, fh, "video/mp4")}, timeout=600)
        body = r.json() if r.ok else {}
        check("video analysis 200 (media_type=video, has frames)",
              r.status_code == 200 and body.get("media_type") == "video" and (body.get("frame_count") or 0) > 0,
              f"{r.status_code} frames={body.get('frame_count')} ms={body.get('processing_ms')}")
    else:
        check("video sample present", False, f"missing {VIDEO_SAMPLE}")

    # 10. Inference latency is SPLIT by media type, and video latency >> image latency
    r = requests.get(f"{base}/api/stats", headers=admin, timeout=30)
    s = r.json() if r.ok else {}
    img_p50, vid_p50 = s.get("image_p50_processing_ms"), s.get("video_p50_processing_ms")
    check("stats split present: image_count>=1 and video_count>=1",
          (s.get("image_count") or 0) >= 1 and (s.get("video_count") or 0) >= 1,
          f"image_count={s.get('image_count')} video_count={s.get('video_count')}")
    check("stats has distinct image vs video latency (video > image)",
          isinstance(img_p50, (int, float)) and isinstance(vid_p50, (int, float)) and vid_p50 > img_p50,
          f"image_p50={img_p50}ms video_p50={vid_p50}ms")

    # 11. End-to-end evaluate job on the built-in set (real YOLO val), polled to completion
    small_id = "small" if "small" in ids else (sorted(ids)[0] if ids else None)
    if small_id and "builtin-detector-redwhite" in ds:
        r = requests.post(f"{base}/api/models/{small_id}/evaluate", headers=admin,
                          json={"dataset_id": "builtin-detector-redwhite", "split": "test"}, timeout=60)
        job = r.json() if r.ok else {}
        job_id = job.get("job_id") or job.get("id")
        ok_enq = r.status_code == 200 and bool(job_id)
        check("evaluate enqueued (job id returned)", ok_enq, f"{r.status_code} job={job_id}")
        final = {}
        if ok_enq:
            for _ in range(120):  # up to ~4 min
                jr = requests.get(f"{base}/api/jobs/{job_id}", headers=admin, timeout=30)
                final = jr.json() if jr.ok else {}
                if final.get("status") in ("succeeded", "failed", "cancelled"):
                    break
                time.sleep(2)
        vm = (final.get("result_json") or final.get("result") or {}).get("val_metrics") or {}
        map50 = vm.get("map50")
        check("evaluate job succeeded with sensible metrics (map50>0.8)",
              final.get("status") == "succeeded" and isinstance(map50, (int, float)) and map50 > 0.8,
              f"status={final.get('status')} map50={map50}")
        # Metric written back onto the model card
        rr = requests.get(f"{base}/api/models", headers=admin, timeout=30)
        card = {m["model_id"]: m for m in (rr.json() if rr.ok else [])}.get(small_id, {})
        cm = (card.get("val_metrics") or {}).get("map50")
        check("evaluated metrics surface on /api/models card", isinstance(cm, (int, float)) and cm > 0.8, f"card map50={cm}")
    else:
        check("evaluate prerequisites present", False, f"small_id={small_id}")

    # 12. Promote swaps the default, then restore
    if "nano" in ids and "small" in ids:
        default_before = next((m["model_id"] for m in models if m.get("is_default")), None)
        r = requests.post(f"{base}/api/models/nano/promote", headers=admin, timeout=60)
        rr = requests.get(f"{base}/api/models", headers=admin, timeout=30).json()
        nano_default = next((m["is_default"] for m in rr if m["model_id"] == "nano"), False)
        check("promote nano makes it the sole default", r.status_code == 200 and nano_default,
              f"{r.status_code} nano_default={nano_default}")
        if default_before:
            requests.post(f"{base}/api/models/{default_before}/promote", headers=admin, timeout=60)
    else:
        check("promote prerequisites present", "nano" in ids and "small" in ids, f"ids={sorted(ids)}")

    # 13. Disable then enable (registry reload path)
    target = "nano" if "nano" in ids and not by_id.get("nano", {}).get("is_default") else None
    if target:
        r = requests.post(f"{base}/api/models/{target}/disable", headers=admin, timeout=60)
        rr = requests.get(f"{base}/api/models", headers=admin, timeout=30).json()
        disabled = next((m.get("disabled") for m in rr if m["model_id"] == target), False)
        check(f"disable {target} sets disabled=true", r.status_code == 200 and disabled, f"{r.status_code} disabled={disabled}")
        requests.post(f"{base}/api/models/{target}/enable", headers=admin, timeout=60)
    else:
        check("disable target available", False, "no non-default nano to disable")

    failed = [n for ok, n, _ in _results if not ok]
    print("\n=== E2E SUMMARY ===")
    print(f"{len(_results) - len(failed)}/{len(_results)} checks passed")
    for n in failed:
        print(f"  FAILED: {n}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
