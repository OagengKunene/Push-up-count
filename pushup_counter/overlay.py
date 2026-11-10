"""OpenCV dashboard with a dedicated statistics panel and pose overlay."""

import textwrap
from typing import Any

from .counter import Snapshot
from .pose import CONNECTIONS, PoseFrame


def draw_dashboard(
    frame: Any,
    pose: PoseFrame,
    snapshot: Snapshot,
    *,
    elapsed: float,
    fps: float,
    goal: int,
    paused: bool,
    variant: str,
    demo: bool,
    tempo=None,
    voice_status: str = "off",
    calibration_stage: str | None = None,
) -> Any:
    import cv2
    import numpy as np

    bg, muted, white, cyan, amber = (
        (18, 23, 32),
        (155, 168, 185),
        (240, 245, 250),
        (215, 213, 68),
        (85, 192, 245),
    )
    height, width = frame.shape[:2]
    canvas = np.full((max(700, height + 190), width + 350, 3), bg, dtype=np.uint8)
    view = frame.copy()
    if pose.landmarks is not None:
        for start, end in CONNECTIONS:
            a, b = pose.landmarks[start], pose.landmarks[end]
            if min(a.visibility or 0, b.visibility or 0) >= 0.5:
                cv2.line(
                    view,
                    (int(a.x * width), int(a.y * height)),
                    (int(b.x * width), int(b.y * height)),
                    cyan,
                    3,
                    cv2.LINE_AA,
                )
        for point in pose.landmarks[11:29]:
            if (point.visibility or 0) >= 0.5:
                cv2.circle(view, (int(point.x * width), int(point.y * height)), 4, white, -1)
    canvas[76 : height + 76, 20 : width + 20] = view

    def label(text: str, x: int, y: int, scale: float = 0.6, color=white, weight: int = 1):
        cv2.putText(
            canvas, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, weight, cv2.LINE_AA
        )

    label("PUSH / UP", 24, 43, 0.95, cyan, 2)
    label("LOCAL POSE TRACKING" if not demo else "SYNTHETIC DEMO", 235, 41, 0.5, muted)
    x = width + 45
    label("CURRENT SET", x, 102, 0.55, muted)
    label(str(snapshot.reps), x, 208, 2.8, white, 4)
    label(f"GOAL  {goal}" if goal else "FULL REPS", x, 240, 0.6, cyan)
    phase = calibration_stage or ("PAUSED" if paused else snapshot.phase.value)
    label(phase, x, 288, 0.72, amber if paused else cyan, 2)
    elbow = f"{snapshot.angle:.0f} deg" if snapshot.angle is not None else "--"
    label(f"ELBOW   {elbow}", x, 330, 0.58)
    label(f"DEPTH   {snapshot.progress * 100:.0f}%", x, 365, 0.58)
    cv2.rectangle(canvas, (x, 382), (x + 260, 395), (50, 61, 76), -1)
    cv2.rectangle(canvas, (x, 382), (x + int(260 * snapshot.progress), 395), cyan, -1)
    label(f"RETRY   {snapshot.rejected}", x, 435, 0.58, muted)
    minutes, seconds = divmod(int(elapsed), 60)
    label(f"TIME    {minutes:02}:{seconds:02}", x, 470, 0.58)
    label(f"FPS     {fps:.1f}", x, 505, 0.58, muted)
    label(f"MODE    {variant.upper()}", x, 540, 0.58, muted)
    if snapshot.last_event and snapshot.last_event.lowering_seconds is not None:
        event = snapshot.last_event
        label(f"SCORE   {event.quality_score:.0f}/100", x, 575, 0.55, cyan)
        label(
            f"D/H/U   {event.lowering_seconds:.1f}/{event.bottom_seconds:.1f}/"
            f"{event.rising_seconds:.1f}s",
            x,
            607,
            0.48,
        )
    if tempo:
        label(f"TARGET  {tempo}", x, 639, 0.48, muted)
    label(f"VOICE   {voice_status.upper()}", x, canvas.shape[0] - 48, 0.45, muted)
    feedback = "Paused - press SPACE to resume" if paused else snapshot.feedback
    if goal and snapshot.reps >= goal:
        feedback = "Goal reached! " + feedback
    for index, line in enumerate(textwrap.wrap(feedback, width=max(35, width // 12))):
        label(line, 25, height + 104 + index * 24, 0.6, amber)
    label(
        "SPACE pause  R new set  M mirror  V voice  D history  Q quit",
        25,
        canvas.shape[0] - 15,
        0.45,
        muted,
    )
    return canvas
