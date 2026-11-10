"""Behavioral regression tests using deterministic movement traces."""

import math
from dataclasses import replace

import pytest

from pushup_counter.config import CounterConfig
from pushup_counter.counter import Observation, Phase, PushUpCounter


class Trace:
    def __init__(self, config=None):
        self.counter = PushUpCounter(config or CounterConfig(smoothing_alpha=1))
        self.time = 0.0
        self.events = []
        self.last = None

    def hold(self, value, seconds=0.3, **kwargs):
        for _ in range(round(seconds / 0.02)):
            observation = None if value is None else Observation(value, **kwargs)
            self.last = self.counter.update(self.time, observation)
            self.time += 0.02
            if self.last.event:
                self.events.append(self.last.event)
        return self

    def rep(self):
        return self.hold(170).hold(130).hold(85).hold(125).hold(170)


def test_complete_rep_and_repeated_top_hold_count_once():
    trace = Trace().rep().hold(170, 2)
    assert trace.counter.reps == 1
    assert len(trace.events) == 1
    assert trace.events[0].accepted
    assert trace.events[0].min_angle == 85


def test_five_complete_reps():
    trace = Trace()
    for _ in range(5):
        trace.rep()
    assert [event.number for event in trace.events] == [1, 2, 3, 4, 5]


def test_starting_at_bottom_does_not_count_half_rep():
    trace = Trace().hold(85).hold(125).hold(170)
    assert trace.counter.reps == 0
    assert trace.counter.phase == Phase.TOP


def test_partial_depth_is_rejected_at_top():
    trace = Trace().hold(170).hold(125).hold(170)
    assert trace.counter.reps == 0
    assert trace.counter.rejected == 1
    assert trace.events[0].reason == "incomplete depth"


def test_single_noisy_bottom_frame_does_not_satisfy_depth():
    trace = Trace().hold(170).hold(130).hold(80, 0.02).hold(130).hold(170)
    assert trace.counter.reps == 0


def test_threshold_jitter_does_not_count():
    trace = Trace().hold(170)
    for _ in range(20):
        trace.hold(150, 0.02).hold(161, 0.02)
    assert trace.counter.reps == 0
    assert trace.counter.phase == Phase.TOP


@pytest.mark.parametrize(
    "error",
    [
        {"body_angle": 110},
        {"body_tilt": 80},
        {"support_ok": False},
        {"confidence": 0.2},
    ],
)
def test_bad_form_cancels_the_unfinished_rep(error):
    trace = Trace().hold(170).hold(130).hold(85, **error).hold(130).hold(170)
    assert trace.counter.reps == 0


def test_long_tracking_loss_cancels_an_unfinished_rep():
    trace = Trace().hold(170).hold(130).hold(85).hold(None, 1).hold(125).hold(170)
    assert trace.counter.reps == 0


def test_short_dropout_freezes_but_does_not_double_count():
    trace = Trace().hold(170).hold(130).hold(85).hold(None, 0.08).hold(125).hold(170)
    assert trace.counter.reps == 1


def test_gap_without_explicit_missing_samples_also_cancels():
    trace = Trace().hold(170).hold(130).hold(85)
    trace.time += 2
    trace.hold(125).hold(170)
    assert trace.counter.reps == 0


def test_side_switch_cannot_join_two_half_reps():
    trace = Trace().hold(170).hold(130).hold(85).hold(125, side="right").hold(170, side="right")
    assert trace.counter.reps == 0


def test_pause_interrupt_requires_new_top_position():
    trace = Trace().hold(170).hold(130).hold(85)
    trace.counter.interrupt()
    trace.hold(125).hold(170)
    assert trace.counter.reps == 0
    trace.rep()
    assert trace.counter.reps == 1


def test_reset_clears_reps_and_unfinished_cycle():
    trace = Trace().rep().hold(130).hold(85)
    trace.counter.reset()
    trace.hold(125).hold(170)
    assert trace.counter.reps == 0
    assert trace.counter.rejected == 0


def test_ui_snapshot_updates_immediately_after_reset_without_consuming_a_frame():
    trace = Trace().rep()
    trace.counter.reset()
    snapshot = trace.counter.snapshot("New set")
    assert snapshot.reps == 0
    assert snapshot.phase == Phase.SEEKING_TOP
    assert snapshot.event is None
    trace.rep()
    assert trace.counter.reps == 1


def test_too_fast_completed_cycle_is_rejected():
    trace = Trace(CounterConfig(smoothing_alpha=1, min_rep_seconds=2))
    trace.rep()
    assert trace.counter.reps == 0
    assert trace.events[0].reason == "movement too fast"


def test_timeout_requires_restart():
    trace = Trace(CounterConfig(smoothing_alpha=1, max_rep_seconds=1))
    trace.hold(170).hold(130).hold(85, 1.5).hold(170)
    assert trace.counter.reps == 0


@pytest.mark.parametrize("value", [math.nan, math.inf, -10, 181])
def test_invalid_angles_do_not_crash_or_count(value):
    trace = Trace().hold(value)
    assert trace.counter.reps == 0
    assert trace.last.angle is None


def test_non_increasing_timestamps_are_rejected():
    counter = PushUpCounter()
    counter.update(1.0, Observation(170))
    with pytest.raises(ValueError, match="increase"):
        counter.update(1.0, Observation(170))


@pytest.mark.parametrize(
    "changes",
    [
        {"up_angle": 90},
        {"down_angle": 170},
        {"smoothing_alpha": 0},
        {"min_body_angle": math.nan},
        {"tracking_timeout": -1},
        {"hysteresis": 80},
    ],
)
def test_invalid_configuration_is_rejected(changes):
    with pytest.raises(ValueError):
        replace(CounterConfig(), **changes)


def test_default_smoothing_still_counts_realistic_tempo():
    trace = Trace(CounterConfig())
    for _ in range(3):
        trace.rep()
    assert trace.counter.reps == 3
