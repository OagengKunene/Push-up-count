import math

import pytest

from pushup_counter.config import CounterConfig
from pushup_counter.counter import Observation, PushUpCounter
from pushup_counter.tempo import TempoTarget, quality_score


@pytest.mark.parametrize("value", ["3-1", "0-1-1", "-1-1-1", "nan-1-1", "8-4-4", "1-1-99"])
def test_invalid_tempos_are_rejected(value):
    with pytest.raises(ValueError):
        TempoTarget.parse(value)


def test_tempo_tolerance_and_actionable_feedback():
    target = TempoTarget.parse("3-1-1")
    assert target.matches(3.1, 1, 1.2)
    assert not target.matches(0.5, 1, 1)
    assert "3 seconds of lowering" in target.feedback(0.5, 1, 1)
    assert str(target) == "3-1-1"


def test_phase_times_sum_to_rep_duration_and_target_is_evaluated():
    counter = PushUpCounter(CounterConfig(smoothing_alpha=1), TempoTarget(0.3, 0.3, 0.3))
    event = None
    timestamp = 0
    for angle in [170, 130, 85, 125, 170]:
        for _ in range(15):
            snapshot = counter.update(timestamp, Observation(angle, body_angle=175))
            if snapshot.event:
                event = snapshot.event
            timestamp += 0.02
    assert event.accepted
    assert event.lowering_seconds > 0
    assert event.bottom_seconds > 0
    assert event.rising_seconds > 0
    assert event.duration == pytest.approx(
        sum((event.lowering_seconds, event.bottom_seconds, event.rising_seconds))
    )
    assert event.tempo_match is True
    assert 0 <= event.quality_score <= 100
    assert counter.snapshot("Next").last_event == event


def test_quality_is_transparent_bounded_and_penalizes_rejected_attempts():
    good = quality_score(180, 170, 85, 160, 95, True)
    bent = quality_score(155, 170, 85, 160, 95, True)
    shallow = quality_score(180, 170, 125, 160, 95, False)
    assert good == 100
    assert 0 <= shallow < bent < good
    assert math.isfinite(bent)
