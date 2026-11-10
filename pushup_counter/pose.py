"""MediaPipe Tasks adapter; no deprecated mp.solutions API."""

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import CounterConfig
from .counter import Observation
from .geometry import angle, horizontal_tilt

# Shoulder, elbow, wrist, hip, knee, ankle, in MediaPipe's 33-landmark schema.
SIDES = {"left": (11, 13, 15, 23, 25, 27), "right": (12, 14, 16, 24, 26, 28)}
CONNECTIONS = (
    (11, 12),
    (11, 13),
    (13, 15),
    (12, 14),
    (14, 16),
    (11, 23),
    (12, 24),
    (23, 24),
    (23, 25),
    (25, 27),
    (24, 26),
    (26, 28),
)


@dataclass
class PoseFrame:
    observation: Observation | None
    landmarks: Any = None


class PoseAnalyzer:
    def __init__(self, config: CounterConfig, variant: str = "standard", side: str = "auto"):
        if variant not in ("standard", "knee") or side not in ("auto", "left", "right"):
            raise ValueError("Unknown push-up variant or tracking side.")
        self.config, self.variant, self.preference = config, variant, side
        self.selected: str | None = None

    def analyze(self, landmarks: Any, width: int, height: int) -> Observation | None:
        if landmarks is None or len(landmarks) < 33:
            return None
        candidates = {}
        for name, indices in SIDES.items():
            needed = indices if self.variant == "standard" else indices[:5]
            points = [landmarks[i] for i in needed]
            if any(not self._visible(p) for p in points):
                continue
            coords = [(p.x * width, p.y * height) for p in points]
            shoulder, elbow, wrist, hip, knee = coords[:5]
            support = coords[-1]
            elbow_angle = angle(shoulder, elbow, wrist)
            body_angle = angle(shoulder, hip, support)
            leg_angle = angle(hip, knee, support) if self.variant == "standard" else 180.0
            if elbow_angle is None or body_angle is None or leg_angle is None:
                continue
            # A side-on view must have a meaningful visible shoulder-to-support span.
            if math.dist(shoulder, support) < min(width, height) * 0.20:
                continue
            candidates[name] = Observation(
                elbow_angle=elbow_angle,
                body_angle=body_angle,
                body_tilt=horizontal_tilt(shoulder, support),
                confidence=min(self._confidence(p) for p in points),
                side=name,
                support_ok=wrist[1] > shoulder[1] and leg_angle >= self.config.min_body_angle,
            )
        if self.preference != "auto":
            return candidates.get(self.preference)
        # Keep the same visible side to avoid mixing joint angles from different arms.
        if self.selected not in candidates:
            self.selected = max(candidates, key=lambda s: candidates[s].confidence, default=None)
        return candidates.get(self.selected)

    @staticmethod
    def _confidence(point: Any) -> float:
        visibility = getattr(point, "visibility", 0.0)
        presence = getattr(point, "presence", 1.0)
        return min(visibility or 0.0, presence if presence is not None else 0.0)

    def _visible(self, point: Any) -> bool:
        return (
            all(math.isfinite(v) for v in (point.x, point.y, self._confidence(point)))
            and 0.01 <= point.x <= 0.99
            and 0.01 <= point.y <= 0.99
            and self._confidence(point) >= self.config.min_visibility
        )


class PoseTracker:
    def __init__(self, model: Path, config: CounterConfig, variant: str, side: str):
        import mediapipe as mp

        self.mp = mp
        self.analyzer = PoseAnalyzer(config, variant, side)
        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(model)),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.6,
            min_pose_presence_confidence=0.6,
            min_tracking_confidence=0.6,
        )
        self.landmarker = mp.tasks.vision.PoseLandmarker.create_from_options(options)
        self._timestamp_ms = -1

    def process(self, frame: Any, timestamp: float) -> PoseFrame:
        import cv2

        self._timestamp_ms = max(self._timestamp_ms + 1, int(timestamp * 1000))
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)
        result = self.landmarker.detect_for_video(image, self._timestamp_ms)
        landmarks = result.pose_landmarks[0] if result.pose_landmarks else None
        height, width = frame.shape[:2]
        return PoseFrame(self.analyzer.analyze(landmarks, width, height), landmarks)

    def close(self) -> None:
        self.landmarker.close()
