"""Local per-attempt CSV and final JSON summary. Camera frames are never logged here."""

import csv
import json
import uuid
from dataclasses import asdict, fields
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
            fieldnames=["set", *[field.name for field in fields(RepEvent)]],
        )
        self.writer.writeheader()
        self.handle.flush()
        self.config, self.source, self.variant = config, source, variant
        self.set_number = 1
        self.accepted = self.rejected = 0
        self.durations: list[float] = []
        self.quality_scores: list[float] = []
        self.phase_times: list[tuple[float, float, float]] = []
        self.tempo_checks: list[bool] = []
        self.metadata: dict = {}

    def new_set(self) -> None:
        self.set_number += 1

    def record(self, event: RepEvent) -> None:
        self.writer.writerow({"set": self.set_number, **asdict(event)})
        self.handle.flush()
        if event.accepted:
            self.accepted += 1
            self.durations.append(event.duration)
            if event.quality_score is not None:
                self.quality_scores.append(event.quality_score)
            if all(
                value is not None
                for value in (event.lowering_seconds, event.bottom_seconds, event.rising_seconds)
            ):
                self.phase_times.append(
                    (event.lowering_seconds, event.bottom_seconds, event.rising_seconds)
                )
            if event.tempo_match is not None:
                self.tempo_checks.append(event.tempo_match)
        else:
            self.rejected += 1

    def close(self, elapsed: float, reason: str = "finished") -> None:
        if self.handle.closed:
            return
        self.handle.close()
        summary = {
            "schema_version": 2,
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
            "mean_quality_score": round(sum(self.quality_scores) / len(self.quality_scores), 1)
            if self.quality_scores
            else None,
            "mean_lowering_seconds": self._phase_mean(0),
            "mean_bottom_seconds": self._phase_mean(1),
            "mean_rising_seconds": self._phase_mean(2),
            "tempo_match_rate": sum(self.tempo_checks) / len(self.tempo_checks)
            if self.tempo_checks
            else None,
            "thresholds": asdict(self.config),
            "rep_csv": self.csv_path.name,
            **self.metadata,
        }
        temporary = self.summary_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.summary_path)

    def _phase_mean(self, index: int) -> float | None:
        return (
            round(sum(row[index] for row in self.phase_times) / len(self.phase_times), 3)
            if self.phase_times
            else None
        )
