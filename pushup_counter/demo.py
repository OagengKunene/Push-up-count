"""Deterministic synthetic input for trying the UI and testing the engine; no AI inference."""

import math

from .counter import Observation
from .pose import PoseFrame


def demo_angle(timestamp: float) -> float:
    phase = timestamp % 3.0
    if phase < 0.5:
        return 172.0
    if phase < 1.2:
        return 172 - (phase - 0.5) / 0.7 * 90
    if phase < 1.6:
        return 82.0
    if phase < 2.3:
        return 82 + (phase - 1.6) / 0.7 * 90
    return 172.0


def demo_frame(timestamp: float):
    import cv2
    import numpy as np

    frame = np.full((540, 900, 3), (27, 34, 45), dtype=np.uint8)
    elbow_angle = demo_angle(timestamp)
    depth = (172 - elbow_angle) / 90
    shoulder = (250, int(195 + depth * 100))
    hip = (490, int(220 + depth * 70))
    ankle = (760, 255)
    elbow = (shoulder[0], shoulder[1] + 105)
    theta = math.radians(elbow_angle)
    wrist = (int(elbow[0] + 100 * math.sin(theta)), int(elbow[1] - 100 * math.cos(theta)))
    for start, end in ((shoulder, hip), (hip, ankle), (shoulder, elbow), (elbow, wrist)):
        cv2.line(frame, start, end, (235, 205, 70), 8, cv2.LINE_AA)
    for point in (shoulder, hip, ankle, elbow, wrist):
        cv2.circle(frame, point, 9, (250, 245, 235), -1, cv2.LINE_AA)
    cv2.circle(frame, (shoulder[0] - 48, shoulder[1] - 8), 30, (235, 205, 70), 4)
    cv2.putText(
        frame,
        "SYNTHETIC DEMO - no camera / no AI inference",
        (35, 65),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (220, 225, 235),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        "One simulated push-up every 3 seconds",
        (35, 100),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (165, 175, 190),
        1,
        cv2.LINE_AA,
    )
    return frame, PoseFrame(Observation(elbow_angle))
