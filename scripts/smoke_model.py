"""Exercise the real downloaded model on blank frames; no webcam/display required."""

import argparse
from pathlib import Path

import numpy as np

from pushup_counter.config import CounterConfig
from pushup_counter.model import ensure_model
from pushup_counter.pose import PoseTracker


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path)
    args = parser.parse_args()
    tracker = PoseTracker(ensure_model(args.model), CounterConfig(), "standard", "auto")
    try:
        for index in range(3):
            result = tracker.process(np.zeros((480, 640, 3), dtype=np.uint8), index / 30)
            assert result.observation is None, (
                "Blank image must not produce an exercise observation"
            )
        print(
            "Verified model: inference succeeded on three blank frames; no false person detected."
        )
    finally:
        tracker.close()


if __name__ == "__main__":
    main()
