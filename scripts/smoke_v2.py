"""Exercise saved calibration, tempo metrics and local history through the public CLI."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    with tempfile.TemporaryDirectory(prefix="pushup-v2-") as directory:
        data = Path(directory)
        env = {**os.environ, "PUSHUP_DATA_DIR": str(data)}

        def run(*args):
            subprocess.run(
                [sys.executable, "-m", "pushup_counter", *map(str, args)],
                env=env,
                check=True,
                timeout=45,
            )

        run("--calibrate", "--demo", "--headless", "--max-frames", 240, "--profile", "demo")
        profile = json.loads((data / "profiles" / "demo.json").read_text())
        assert profile["up_angle"] == 164 and profile["down_angle"] == 90
        run(
            "--demo",
            "--headless",
            "--demo-seconds",
            6,
            "--profile",
            "demo",
            "--tempo",
            "0.7-0.4-0.7",
        )
        summary = json.loads(next((data / "workouts").glob("*_summary.json")).read_text())
        assert summary["accepted_reps"] == 2, summary
        assert summary["mean_quality_score"] is not None
        assert summary["mean_lowering_seconds"] > 0
        run("--dashboard", "--no-open")
        report = data / "reports" / "dashboard.html"
        assert report.exists() and "__WORKOUT_DATA__" not in report.read_text(encoding="utf-8")
        print("V2 end-to-end checks passed: calibration, tempo, scoring, logs and history.")


if __name__ == "__main__":
    main()
