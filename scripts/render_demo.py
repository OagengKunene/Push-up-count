"""Reproduce the README's explicitly synthetic interface screenshot."""

from pathlib import Path

import cv2

from pushup_counter.counter import PushUpCounter
from pushup_counter.demo import demo_frame
from pushup_counter.overlay import draw_dashboard


def main() -> None:
    counter = PushUpCounter()
    for index in range(225):
        timestamp = index / 30
        frame, pose = demo_frame(timestamp)
        snapshot = counter.update(timestamp, pose.observation)
    dashboard = draw_dashboard(
        frame,
        pose,
        snapshot,
        elapsed=timestamp,
        fps=30,
        goal=20,
        paused=False,
        variant="standard",
        demo=True,
    )
    target = Path(__file__).resolve().parents[1] / "docs" / "demo.png"
    target.parent.mkdir(exist_ok=True)
    if not cv2.imwrite(str(target), dashboard):
        raise RuntimeError("Cannot write the demo screenshot")
    print(target)


if __name__ == "__main__":
    main()
