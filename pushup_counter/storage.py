"""Local per-attempt CSV and final JSON summary. Camera frames are never logged here."""

import csv
import json
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from .config import CounterConfig
from .counter import RepEvent


class WorkoutLog:
    def __init__(self, directory: Path, config: CounterConfig, source: str, variant: str):
        directory.mkdir(parents=True, exist_ok=True)
        self.started = datetime.now(UTC).isoformat()
        name = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8]
        self.csv_path = directory / f"{name}_reps.csv"
        self.summary_path = directory / f"{name}_summary.json"
        self.handle = self.csv_path.open("x", newline="", encoding="utf-8")
        self.writer = csv.DictWriter(
            self.handle,
            fieldnames=[
                "set",
                "number",
                "timestamp",
                "duration",
                "min_angle",
                "accepted",
                "reason",
            ],
        )
        self.writer.writeheader()
        self.handle.flush()
        self.config, self.source, self.variant = config, source, variant
        self.set_number = 1
        self.accepted = self.rejected = 0
        self.durations: list[float] = []

    def new_set(self) -> None:
        self.set_number += 1

    def record(self, event: RepEvent) -> None:
        self.writer.writerow({"set": self.set_number, **asdict(event)})
        self.handle.flush()
        if event.accepted:
            self.accepted += 1
            self.durations.append(event.duration)
        else:
            self.rejected += 1

    def close(self, elapsed: float, reason: str = "finished") -> None:
        if self.handle.closed:
            return
        self.handle.close()
        summary = {
            "started_utc": self.started,
            "ended_utc": datetime.now(UTC).isoformat(),
            "source": self.source,
            "variant": self.variant,
            "sets": self.set_number,
            "accepted_reps": self.accepted,
            "rejected_attempts": self.rejected,
            "elapsed_seconds": round(elapsed, 3),
            "mean_rep_seconds": round(sum(self.durations) / len(self.durations), 3)
            if self.durations
            else None,
            "end_reason": reason,
            "thresholds": asdict(self.config),
            "rep_csv": self.csv_path.name,
        }
        temporary = self.summary_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.summary_path)
