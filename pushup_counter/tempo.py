"""Transparent tempo matching and a bounded, pose-based rep quality heuristic."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class TempoTarget:
    lowering: float
    bottom: float
    rising: float

    def __post_init__(self):
        values = (self.lowering, self.bottom, self.rising)
        if not all(math.isfinite(v) and 0 <= v <= 10 for v in values):
            raise ValueError("Tempo values must be finite seconds from 0 to 10.")
        if self.lowering <= 0 or self.rising <= 0 or sum(values) > 12:
            raise ValueError("Lowering/rising must be positive; total target tempo must be <=12s.")

    @classmethod
    def parse(cls, value: str) -> "TempoTarget":
        try:
            parts = [float(part) for part in value.split("-")]
            if len(parts) != 3:
                raise ValueError()
            return cls(*parts)
        except (TypeError, ValueError) as exc:
            raise ValueError("Use a tempo such as 3-1-1 (lower-hold-rise seconds).") from exc

    def matches(self, lowering: float, bottom: float, rising: float) -> bool:
        return all(
            abs(measured - target) <= max(0.35, target * 0.30)
            for measured, target in zip(
                (lowering, bottom, rising), (self.lowering, self.bottom, self.rising), strict=True
            )
        )

    def feedback(self, lowering: float, bottom: float, rising: float) -> str:
        for name, measured, target in zip(
            ("lowering", "bottom hold", "rising"),
            (lowering, bottom, rising),
            (self.lowering, self.bottom, self.rising),
            strict=True,
        ):
            if abs(measured - target) > max(0.35, target * 0.30):
                return f"Aim for {target:g} seconds of {name}"
        return "Tempo on target"

    def __str__(self):
        return f"{self.lowering:g}-{self.bottom:g}-{self.rising:g}"


def quality_score(
    min_body: float, lockout: float, min_angle: float, up: float, down: float, accepted: bool
) -> float:
    """Depth 40%, alignment 40%, lockout 20%; no clinical/biomechanical claim."""
    depth = min(1.0, max(0.0, (up - min_angle) / max(up - down, 1)))
    alignment = min(1.0, max(0.0, (min_body - 130) / 45))
    extension = min(1.0, max(0.0, lockout / max(up, 1)))
    score = round(40 * depth + 40 * alignment + 20 * extension, 1)
    return score if accepted else min(score, 59.0)
