# Local model weights

Model binaries are intentionally ignored by Git.

- `models/base/` stores local base weights such as `yolov26m.pt`, `yolo26n.pt`, and `yolo11n.pt`.
- `models/serving/best.pt` is the model loaded by the FastAPI backend by default.

To prepare the local backend from the small local base weight:

```powershell
Copy-Item models\base\yolo26n.pt models\serving\best.pt -Force
```

For the preferred YOLOv26m workflow, place or copy the chosen trained checkpoint into `models/serving/best.pt`.
