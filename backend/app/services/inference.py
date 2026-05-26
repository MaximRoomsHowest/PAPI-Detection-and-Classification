from collections import Counter, deque
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.config import Settings
from app.validation.schemas import AnalysisPayload, LampResult
from app.services.angle import compute_elevation_angles, extract_gps_metadata, unavailable_angle
from app.services.state import confidence_from_lamps, global_state_from_lamps, normalize_detections


class InferenceService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._model: Any | None = None

    def analyze(
        self,
        media_path: Path,
        media_type: str,
        runway_id: str,
        original_filename: str,
        drone_id: str | None = None,
        drone_metadata: tuple[float, float, float] | None = None,
    ) -> AnalysisPayload:
        if media_type == "image":
            return self.analyze_image(media_path, runway_id, original_filename, drone_id, drone_metadata)
        if media_type == "video":
            return self.analyze_video(media_path, runway_id, original_filename, drone_id, drone_metadata)
        raise ValueError(f"Unsupported media type: {media_type}")

    @property
    def model(self) -> Any:
        if self._model is None:
            try:
                from ultralytics import YOLO
            except ImportError as exc:
                raise RuntimeError("Ultralytics is not installed. Run `pip install -r requirements.txt`.") from exc
            if not self.settings.model_path.exists():
                raise RuntimeError(f"Model file not found: {self.settings.model_path}")
            self._model = YOLO(str(self.settings.model_path))
        return self._model

    def analyze_image(
        self,
        media_path: Path,
        runway_id: str,
        original_filename: str,
        drone_id: str | None,
        drone_metadata: tuple[float, float, float] | None,
    ) -> AnalysisPayload:
        cv2 = self._require_cv2()
        start = perf_counter()
        frame = cv2.imread(str(media_path))
        if frame is None:
            raise ValueError("Could not read uploaded image.")
        frame_height, frame_width = frame.shape[:2]

        detections = self._detect_frame(frame, use_tracking=False)
        lamps = normalize_detections(detections)
        global_state = global_state_from_lamps(lamps)
        confidence = confidence_from_lamps(lamps)
        angle = self._angle_for_media(media_path, runway_id, drone_metadata)

        annotated = self._draw_overlay(frame, lamps, global_state, confidence, angle.elevation_angle_deg)
        artifact_path = self.settings.exports_dir / f"{uuid4()}_annotated.jpg"
        cv2.imwrite(str(artifact_path), annotated)

        processing_ms = int((perf_counter() - start) * 1000)
        return AnalysisPayload(
            media_type="image",
            original_filename=original_filename,
            runway_id=runway_id,
            drone_id=drone_id,
            global_state=global_state,
            lamps=lamps,
            confidence=confidence,
            frame_width=frame_width,
            frame_height=frame_height,
            frame_count=1,
            processing_ms=processing_ms,
            angle=angle,
            artifact_url=f"/media/{artifact_path.name}",
            detections=detections,
        )

    def analyze_video(
        self,
        media_path: Path,
        runway_id: str,
        original_filename: str,
        drone_id: str | None,
        drone_metadata: tuple[float, float, float] | None,
    ) -> AnalysisPayload:
        cv2 = self._require_cv2()
        start = perf_counter()
        cap = cv2.VideoCapture(str(media_path))
        if not cap.isOpened():
            raise ValueError("Could not read uploaded video.")

        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 15
        artifact_path = self.settings.exports_dir / f"{uuid4()}_annotated.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(artifact_path), fourcc, fps, (frame_width, frame_height))

        history = deque(maxlen=self.settings.video_history_size)
        all_states: list[str] = []
        all_confidences: list[float] = []
        lamp_history: dict[int, list[LampResult]] = {1: [], 2: [], 3: [], 4: []}
        frame_count = 0
        angle = self._angle_for_media(media_path, runway_id, drone_metadata)
        last_detections: list[dict] = []

        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break

                detections = self._detect_frame(frame, use_tracking=True)
                lamps = normalize_detections(detections)
                frame_state = global_state_from_lamps(lamps)
                frame_confidence = confidence_from_lamps(lamps)

                history.append(frame_state)
                smoothed_state = Counter(history).most_common(1)[0][0]
                annotated = self._draw_overlay(
                    frame,
                    lamps,
                    smoothed_state,
                    frame_confidence,
                    angle.elevation_angle_deg,
                )
                writer.write(annotated)

                for lamp in lamps:
                    lamp_history[lamp.index].append(lamp)
                last_detections = detections
                all_states.append(smoothed_state)
                all_confidences.append(frame_confidence)
                frame_count += 1
        finally:
            cap.release()
            writer.release()

        if frame_count == 0:
            raise ValueError("Uploaded video did not contain readable frames.")

        final_lamps = self._aggregate_video_lamps(lamp_history)
        global_state = global_state_from_lamps(final_lamps)
        confidence = confidence_from_lamps(final_lamps)
        processing_ms = int((perf_counter() - start) * 1000)

        return AnalysisPayload(
            media_type="video",
            original_filename=original_filename,
            runway_id=runway_id,
            drone_id=drone_id,
            global_state=global_state,
            lamps=final_lamps,
            confidence=confidence,
            frame_width=frame_width,
            frame_height=frame_height,
            frame_count=frame_count,
            processing_ms=processing_ms,
            angle=angle,
            artifact_url=f"/media/{artifact_path.name}",
            detections=last_detections,
        )

    @staticmethod
    def _aggregate_video_lamps(lamp_history: dict[int, list[LampResult]]) -> list[LampResult]:
        final_lamps: list[LampResult] = []
        for index in range(1, 5):
            history = lamp_history.get(index, [])
            known = [lamp for lamp in history if lamp.state != "unknown"]
            if not known:
                final_lamps.append(LampResult(index=index, state="unknown", confidence=0.0))
                continue

            state = Counter(lamp.state for lamp in known).most_common(1)[0][0]
            matching = [lamp for lamp in known if lamp.state == state]
            confidence = round(sum(lamp.confidence for lamp in matching) / len(matching), 4)
            bbox = next((lamp.bbox for lamp in reversed(matching) if lamp.bbox is not None), None)
            final_lamps.append(
                LampResult(
                    index=index,
                    state=state,
                    confidence=confidence,
                    bbox=bbox,
                )
            )
        return final_lamps

    def _detect_frame(self, frame: Any, use_tracking: bool) -> list[dict]:
        if use_tracking:
            results = self.model.track(
                frame,
                persist=True,
                tracker="bytetrack.yaml",
                conf=self.settings.confidence_threshold,
                verbose=False,
            )
        else:
            results = self.model.predict(
                frame,
                conf=self.settings.confidence_threshold,
                verbose=False,
            )

        if not results:
            return []

        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return []

        detections: list[dict] = []
        for box in boxes:
            x1, y1, x2, y2 = [int(value) for value in box.xyxy[0]]
            detections.append(
                {
                    "class_id": int(box.cls[0]),
                    "confidence": round(float(box.conf[0]), 4),
                    "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                }
            )
        return detections

    def _angle_for_media(
        self,
        media_path: Path,
        runway_id: str,
        drone_metadata: tuple[float, float, float] | None,
    ):
        angle_source = "request_metadata" if drone_metadata else "file_metadata"
        metadata = drone_metadata or extract_gps_metadata(media_path)
        if metadata is None:
            return unavailable_angle(
                "GPS/altitude metadata not available. Browser uploads usually preserve the original file bytes, "
                "but many exported/compressed videos and images do not contain drone telemetry."
            )
        latitude, longitude, altitude = metadata
        return compute_elevation_angles(latitude, longitude, altitude, runway_id, angle_source=angle_source)

    def _draw_overlay(
        self,
        frame: Any,
        lamps: list,
        global_state: str,
        confidence: float,
        elevation_angle_deg: float | None,
    ) -> Any:
        cv2 = self._require_cv2()
        for lamp in lamps:
            if lamp.bbox is None:
                continue
            color = (245, 245, 245) if lamp.state == "white" else (0, 0, 255)
            cv2.rectangle(frame, (lamp.bbox.x1, lamp.bbox.y1), (lamp.bbox.x2, lamp.bbox.y2), color, 2)
            cv2.putText(
                frame,
                f"L{lamp.index}: {lamp.state} {lamp.confidence:.2f}",
                (lamp.bbox.x1, max(24, lamp.bbox.y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                color,
                2,
            )

        angle_text = "angle: unavailable" if elevation_angle_deg is None else f"angle: {elevation_angle_deg:.3f} deg"
        lines = [
            f"PAPI: {global_state}",
            f"confidence: {confidence:.2f}",
            angle_text,
        ]
        y = 40
        for line in lines:
            cv2.putText(frame, line, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 0), 2)
            y += 36
        return frame

    @staticmethod
    def _require_cv2():
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("OpenCV is not installed. Run `pip install -r requirements.txt`.") from exc
        return cv2


@lru_cache
def get_inference_service() -> InferenceService:
    from app.config import get_settings

    return InferenceService(get_settings())
