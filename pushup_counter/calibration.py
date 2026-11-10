"""Guided, stable top/bottom holds with bounded thresholds and reusable profiles."""

import json
import math
import re
import statistics
import tempfile
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from .config import CounterConfig
from .counter import Observation


@dataclass(frozen=True)
class CalibrationProfile:
    name: str
    variant: str
    up_angle: float
    down_angle: float
    top_median: float
    bottom_median: float
    created_utc: str
    source: str = "webcam"
    schema_version: int = 1

    def validate(self) -> None:
        profile_filename(self.name)
        if self.variant not in ("standard", "knee") or self.schema_version != 1:
            raise ValueError("Unsupported calibration profile.")
        if self.source not in ("webcam", "video", "synthetic demo"):
            raise ValueError("Unsupported calibration source.")
        if not all(
            math.isfinite(v)
            for v in (self.up_angle, self.down_angle, self.top_median, self.bottom_median)
        ):
            raise ValueError("Calibration values must be finite.")
        if not 145 <= self.up_angle <= 175 or not 60 <= self.down_angle <= 110:
            raise ValueError("Calibrated thresholds are outside the supported range.")
        if not 145 <= self.top_median <= 180 or not 45 <= self.bottom_median <= 120:
            raise ValueError("Calibration poses are outside the supported range.")
        CounterConfig(up_angle=self.up_angle, down_angle=self.down_angle)

    def apply(self, config: CounterConfig) -> CounterConfig:
        self.validate()
        return replace(config, up_angle=self.up_angle, down_angle=self.down_angle)


def profile_filename(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", name):
        raise ValueError("Profile names use 1-40 letters, numbers, hyphens or underscores.")
    return name + ".json"


def load_profile(directory: Path, name: str) -> CalibrationProfile | None:
    path = directory / profile_filename(name)
    if not path.exists():
        return None
    try:
        if path.stat().st_size > 16384:
            raise ValueError("Profile file is too large.")
        profile = CalibrationProfile(**json.loads(path.read_text(encoding="utf-8")))
        profile.validate()
        if profile.name != name:
            raise ValueError("Profile name does not match its filename.")
        return profile
    except (TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid calibration profile: {path}") from exc


def save_profile(directory: Path, profile: CalibrationProfile) -> Path:
    profile.validate()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / profile_filename(profile.name)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=directory, suffix=".tmp", encoding="utf-8", delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(asdict(profile), handle, indent=2)
            handle.write("\n")
        temporary.replace(target)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    return target


@dataclass(frozen=True)
class CalibrationStatus:
    stage: str
    prompt: str
    progress: float
    profile: CalibrationProfile | None = None


class CalibrationWizard:
    HOLD_SECONDS = 2.0
    MIN_SAMPLES = 15
    MAX_SPREAD = 8.0

    def __init__(self, config: CounterConfig, name: str, variant: str, source: str = "webcam"):
        profile_filename(name)
        self.config, self.name, self.variant = config, name, variant
        self.source = source
        self.stage = "TOP"
        self.samples: list[float] = []
        self.since: float | None = None
        self.previous: float | None = None
        self.side: str | None = None
        self.top: float | None = None
        self.profile: CalibrationProfile | None = None

    def _clear_hold(self) -> None:
        self.samples.clear()
        self.since = None

    def update(self, timestamp: float, observation: Observation | None) -> CalibrationStatus:
        if (
            not math.isfinite(timestamp)
            or timestamp < 0
            or (self.previous is not None and timestamp <= self.previous)
        ):
            raise ValueError("Calibration timestamps must strictly increase.")
        gap = self.previous is not None and timestamp - self.previous > 0.25
        self.previous = timestamp
        if self.profile:
            return CalibrationStatus("DONE", "Calibration saved - ready to train", 1, self.profile)
        valid = observation is not None and all(
            math.isfinite(v)
            for v in (
                observation.elbow_angle,
                observation.body_angle,
                observation.body_tilt,
                observation.confidence,
            )
        )
        valid = valid and (
            self.config.min_visibility <= observation.confidence <= 1
            and self.config.min_body_angle <= observation.body_angle <= 180
            and 0 <= observation.body_tilt <= self.config.max_body_tilt
            and observation.support_ok
        )
        if not valid:
            self._clear_hold()
            return CalibrationStatus(self.stage, "Keep your full side visible and body aligned", 0)
        if self.side is not None and observation.side != self.side:
            self._clear_hold()
            # Both holds must describe the same arm/camera view.
            self.stage, self.top = "TOP", None
        self.side = observation.side
        if gap:
            self._clear_hold()
        current = observation.elbow_angle
        expected = 145 <= current <= 180 if self.stage == "TOP" else 45 <= current <= 120
        prompt = (
            "Hold a straight-arm plank for 2 seconds"
            if self.stage == "TOP"
            else ("Lower to your bottom position; hold for 2 seconds")
        )
        if not expected:
            self._clear_hold()
            return CalibrationStatus(self.stage, prompt, 0)
        if self.since is None:
            self.since = timestamp
        self.samples.append(current)
        if max(self.samples) - min(self.samples) > self.MAX_SPREAD:
            self._clear_hold()
            return CalibrationStatus(self.stage, "Hold still - keep the elbow angle steady", 0)
        progress = min(1.0, (timestamp - self.since) / self.HOLD_SECONDS)
        if progress >= 1 - 1e-9 and len(self.samples) >= self.MIN_SAMPLES:
            median = statistics.median(self.samples)
            self._clear_hold()
            if self.stage == "TOP":
                self.top, self.stage = median, "BOTTOM"
                return CalibrationStatus("BOTTOM", "Top captured - lower and hold the bottom", 0)
            up, down = max(145.0, min(175.0, self.top - 8)), max(60.0, min(110.0, median + 8))
            if up - down < 35:
                return CalibrationStatus(
                    "BOTTOM", "Range is too small - lower further and retry", 0
                )
            self.profile = CalibrationProfile(
                self.name,
                self.variant,
                up,
                down,
                self.top,
                median,
                datetime.now(UTC).isoformat(),
                self.source,
            )
            self.profile.validate()
            self.stage = "DONE"
            return CalibrationStatus(
                "DONE", "Calibration complete - profile ready", 1, self.profile
            )
        return CalibrationStatus(self.stage, prompt, progress)
