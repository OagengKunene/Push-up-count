"""Temporal push-up state machine, testable without OpenCV, MediaPipe or a webcam."""

import math
from dataclasses import dataclass
from enum import StrEnum

from .config import CounterConfig


class Phase(StrEnum):
    SEEKING_TOP = "FIND TOP"
    TOP = "TOP"
    LOWERING = "LOWERING"
    BOTTOM = "BOTTOM"
    RISING = "RISING"


@dataclass(frozen=True)
class Observation:
    elbow_angle: float
    body_angle: float = 180.0
    body_tilt: float = 0.0
    confidence: float = 1.0
    side: str = "left"
    support_ok: bool = True


@dataclass(frozen=True)
class RepEvent:
    number: int
    timestamp: float
    duration: float
    min_angle: float
    accepted: bool
    reason: str


@dataclass(frozen=True)
class Snapshot:
    reps: int
    rejected: int
    phase: Phase
    angle: float | None
    progress: float
    feedback: str
    event: RepEvent | None = None


class PushUpCounter:
    def __init__(self, config: CounterConfig | None = None) -> None:
        self.config = config or CounterConfig()
        self.reps = 0
        self.rejected = 0
        self._last_timestamp: float | None = None
        self._last_seen: float | None = None
        self._side: str | None = None
        self._clear_cycle()

    def _clear_cycle(self) -> None:
        self.phase = Phase.SEEKING_TOP
        self.smoothed: float | None = None
        self._started: float | None = None
        self._min_angle = 180.0
        self._candidate: str | None = None
        self._candidate_since = 0.0

    def interrupt(self) -> None:
        """Pause/side changes/tracking gaps must never bridge two halves of a rep."""
        self._clear_cycle()
        self._last_seen = None

    def reset(self) -> None:
        self.reps = self.rejected = 0
        self.interrupt()
        self._side = None

    def _held(self, name: str, timestamp: float) -> bool:
        if self._candidate != name:
            self._candidate = name
            self._candidate_since = timestamp
        return timestamp - self._candidate_since + 1e-9 >= self.config.hold_seconds

    def _snapshot(self, feedback: str, event: RepEvent | None = None) -> Snapshot:
        cfg = self.config
        progress = (
            0.0
            if self.smoothed is None
            else max(
                0.0, min(1.0, (cfg.up_angle - self.smoothed) / (cfg.up_angle - cfg.down_angle))
            )
        )
        return Snapshot(
            self.reps, self.rejected, self.phase, self.smoothed, progress, feedback, event
        )

    def snapshot(self, feedback: str) -> Snapshot:
        """Read current state after a UI action without consuming another video frame."""
        return self._snapshot(feedback)

    def update(self, timestamp: float, observation: Observation | None) -> Snapshot:
        if not math.isfinite(timestamp) or timestamp < 0:
            raise ValueError("Timestamp must be finite and non-negative.")
        if self._last_timestamp is not None and timestamp <= self._last_timestamp:
            raise ValueError("Timestamps must strictly increase.")
        self._last_timestamp = timestamp
        cfg = self.config

        if self._last_seen is not None and timestamp - self._last_seen > cfg.tracking_timeout:
            self.interrupt()
        if observation is None or not self._usable(observation):
            self._candidate = None
            return self._snapshot("Keep your whole body in view; improve lighting")
        self._last_seen = timestamp
        if self._side is not None and self._side != observation.side:
            self._clear_cycle()
        self._side = observation.side

        form_error = self._form_error(observation)
        if form_error:
            # Do not let a bent-body movement or standing arm curl enter the state machine.
            self._clear_cycle()
            return self._snapshot(form_error)

        raw = observation.elbow_angle
        self.smoothed = (
            raw
            if self.smoothed is None
            else (cfg.smoothing_alpha * raw + (1 - cfg.smoothing_alpha) * self.smoothed)
        )
        current = self.smoothed
        event = None
        feedback = "Lower with control"
        if self.phase == Phase.SEEKING_TOP:
            feedback = "Start in a straight-arm plank"
            if current >= cfg.up_angle:
                if self._held("start", timestamp):
                    self.phase = Phase.TOP
                    self._candidate = None
                    feedback = "Ready - lower your body"
            else:
                self._candidate = None
        elif self.phase == Phase.TOP:
            if current < cfg.up_angle - cfg.hysteresis:
                self.phase = Phase.LOWERING
                self._started = timestamp
                self._min_angle = current
                self._candidate = None
        else:
            self._min_angle = min(self._min_angle, current)
            if self._started is not None and timestamp - self._started > cfg.max_rep_seconds:
                self.interrupt()
                return self._snapshot("Rep timed out - return to a straight-arm plank")
            if current <= cfg.down_angle:
                if self._held("bottom", timestamp):
                    self.phase = Phase.BOTTOM
                    feedback = "Depth reached - push up"
            elif current >= cfg.up_angle:
                if self._held("finish", timestamp):
                    duration = timestamp - self._started if self._started is not None else 0.0
                    reached_bottom = self.phase in (Phase.BOTTOM, Phase.RISING)
                    accepted = reached_bottom and duration >= cfg.min_rep_seconds
                    reason = (
                        "full rep"
                        if accepted
                        else ("incomplete depth" if not reached_bottom else "movement too fast")
                    )
                    if accepted:
                        self.reps += 1
                    else:
                        self.rejected += 1
                    event = RepEvent(
                        self.reps, timestamp, duration, self._min_angle, accepted, reason
                    )
                    self.phase = Phase.TOP
                    self._started = None
                    self._candidate = None
                    feedback = f"Rep {self.reps} counted" if accepted else f"Try again: {reason}"
            else:
                self._candidate = None
                if self.phase == Phase.BOTTOM and current > cfg.down_angle + cfg.hysteresis:
                    self.phase = Phase.RISING
                feedback = "Push back to straight arms" if self.phase == Phase.RISING else feedback
        return self._snapshot(feedback, event)

    @staticmethod
    def _usable(observation: Observation) -> bool:
        return (
            all(
                math.isfinite(value)
                for value in (
                    observation.elbow_angle,
                    observation.body_angle,
                    observation.body_tilt,
                    observation.confidence,
                )
            )
            and 0 <= observation.elbow_angle <= 180
            and 0 <= observation.body_angle <= 180
            and 0 <= observation.body_tilt <= 90
            and 0 <= observation.confidence <= 1
        )

    def _form_error(self, observation: Observation) -> str | None:
        if observation.confidence < self.config.min_visibility:
            return "Tracking uncertain - keep the visible side in view"
        if observation.body_tilt > self.config.max_body_tilt:
            return "Place the camera to your side; hold a horizontal plank"
        if observation.body_angle < self.config.min_body_angle:
            return "Keep shoulders, hips and support point aligned"
        if not observation.support_ok:
            return "Keep legs straight and hands under your shoulders"
        return None
