"""Explicit, validated counting thresholds. These are heuristics, not clinical measurements."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CounterConfig:
    up_angle: float = 160.0
    down_angle: float = 95.0
    hysteresis: float = 12.0
    hold_seconds: float = 0.12
    min_rep_seconds: float = 0.6
    max_rep_seconds: float = 15.0
    tracking_timeout: float = 0.65
    smoothing_alpha: float = 0.45
    min_body_angle: float = 155.0
    max_body_tilt: float = 40.0
    min_visibility: float = 0.55

    def __post_init__(self) -> None:
        if not all(math.isfinite(value) for value in vars(self).values()):
            raise ValueError("All thresholds must be finite numbers.")
        if not 20 <= self.down_angle < self.up_angle <= 180:
            raise ValueError("Use 20 <= down angle < up angle <= 180.")
        if not 0 < self.hysteresis < (self.up_angle - self.down_angle) / 2:
            raise ValueError("Hysteresis must be positive and smaller than half the angle range.")
        if not 0 < self.hold_seconds < self.min_rep_seconds < self.max_rep_seconds:
            raise ValueError("Require 0 < hold time < minimum rep time < maximum rep time.")
        if self.tracking_timeout <= 0:
            raise ValueError("Tracking timeout must be positive.")
        if not 0 < self.smoothing_alpha <= 1:
            raise ValueError("Smoothing alpha must be in (0, 1].")
        if not 90 <= self.min_body_angle <= 180:
            raise ValueError("Minimum body angle must be between 90 and 180.")
        if not 0 < self.max_body_tilt < 90:
            raise ValueError("Maximum body tilt must be between 0 and 90.")
        if not 0 < self.min_visibility <= 1:
            raise ValueError("Minimum landmark confidence must be in (0, 1].")
