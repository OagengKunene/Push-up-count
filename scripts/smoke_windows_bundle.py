"""Verify the actual EXE's launcher, calibration, counting, model and report resources."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np


def main():
    root = Path(__file__).resolve().parents[1]
    exe = root / "dist" / "PushUpCounter" / "PushUpCounter.exe"
    with tempfile.TemporaryDirectory(prefix="pushup-bundle-smoke-") as directory:
        data = Path(directory)
        env = {**os.environ, "PUSHUP_DATA_DIR": str(data)}

        def run(*args):
            subprocess.run([str(exe), *map(str, args)], env=env, check=True, timeout=90)

        run("--desktop-smoke")
        run("--demo", "--calibrate", "--headless", "--max-frames", 240, "--profile", "bundle_demo")
        assert (data / "profiles" / "bundle_demo.json").exists()
        run(
            "--demo",
            "--headless",
            "--demo-seconds",
            6,
            "--profile",
            "bundle_demo",
            "--tempo",
            "0.7-0.4-0.7",
        )
        summaries = list((data / "workouts").glob("*_summary.json"))
        summary = json.loads(summaries[0].read_text())
        assert summary["accepted_reps"] == 2, summary
        assert summary["mean_lowering_seconds"] is not None
        assert summary["mean_quality_score"] is not None
        fixture = data / "blank.avi"
        writer = cv2.VideoWriter(str(fixture), cv2.VideoWriter_fourcc(*"MJPG"), 30, (640, 480))
        assert writer.isOpened()
        for _ in range(3):
            writer.write(np.zeros((480, 640, 3), dtype=np.uint8))
        writer.release()
        run(
            "--video",
            fixture,
            "--headless",
            "--offline",
            "--max-frames",
            3,
            "--log-dir",
            data / "model-logs",
        )
        model_summary = json.loads(next((data / "model-logs").glob("*_summary.json")).read_text())
        assert model_summary["processed_frames"] == 3
        assert model_summary["accepted_reps"] == 0
        report = data / "history.html"
        run("--dashboard", "--no-open", "--dashboard-output", report)
        assert "Every rep adds up" in report.read_text(encoding="utf-8")
        assert '"reps": 2' in report.read_text(encoding="utf-8")
        run("--check-voice")
        (root / "dist" / "BUNDLE_VALIDATION.json").write_text(
            json.dumps(
                {
                    "launcher": "passed",
                    "calibration": "passed",
                    "synthetic_reps": 2,
                    "offline_model_inference": "passed",
                    "history_resources": "passed",
                    "windows_speech_engine": "passed",
                    "python_installation_required": False,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print("Windows EXE checks passed: launcher, calibration, tempo, speech, model and history.")


if __name__ == "__main__":
    main()
