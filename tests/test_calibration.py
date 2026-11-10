import json
from dataclasses import replace

import pytest

from pushup_counter.calibration import (
    CalibrationWizard,
    load_profile,
    profile_filename,
    save_profile,
)
from pushup_counter.config import CounterConfig
from pushup_counter.counter import Observation


def hold(wizard, start, angle, samples=70, **kwargs):
    result = None
    for index in range(samples):
        result = wizard.update(start + index / 30, Observation(angle, **kwargs))
    return result


def test_two_stable_holds_produce_bounded_reusable_profile(tmp_path):
    wizard = CalibrationWizard(CounterConfig(), "side_view", "standard")
    hold(wizard, 0, 172)
    result = hold(wizard, 3, 82)
    profile = result.profile
    assert profile.up_angle == 164
    assert profile.down_angle == 90
    save_profile(tmp_path, profile)
    assert load_profile(tmp_path, "side_view") == profile
    assert profile.apply(CounterConfig()).up_angle == 164


def test_unstable_holds_do_not_calibrate():
    wizard = CalibrationWizard(CounterConfig(), "default", "standard")
    for index in range(180):
        wizard.update(index / 30, Observation(150 if index % 2 else 175))
    assert wizard.top is None


def test_occlusion_resets_hold_instead_of_joining_disconnected_samples():
    wizard = CalibrationWizard(CounterConfig(), "default", "standard")
    hold(wizard, 0, 172, samples=40)
    wizard.update(1.4, None)
    hold(wizard, 1.5, 172, samples=40)
    assert wizard.top is None


def test_switching_arms_restarts_both_holds():
    wizard = CalibrationWizard(CounterConfig(), "default", "standard")
    hold(wizard, 0, 172)
    hold(wizard, 3, 82, side="right")
    assert wizard.top is None
    assert wizard.stage == "TOP"


@pytest.mark.parametrize(
    "kwargs", [{"body_angle": 120}, {"body_tilt": 80}, {"confidence": 0.2}, {"support_ok": False}]
)
def test_bad_form_cannot_be_learned_as_a_calibration(kwargs):
    wizard = CalibrationWizard(CounterConfig(), "default", "standard")
    hold(wizard, 0, 172, **kwargs)
    assert wizard.top is None


@pytest.mark.parametrize("name", ["../escape", "", "with spaces", "a/b", "a\\b", "x" * 41])
def test_profile_names_cannot_escape_the_profile_directory(name):
    with pytest.raises(ValueError):
        profile_filename(name)


def test_invalid_profile_does_not_overwrite_previous_calibration(tmp_path):
    wizard = CalibrationWizard(CounterConfig(), "default", "standard")
    hold(wizard, 0, 172)
    profile = hold(wizard, 3, 82).profile
    path = save_profile(tmp_path, profile)
    before = path.read_bytes()
    with pytest.raises(ValueError):
        save_profile(tmp_path, replace(profile, down_angle=170))
    assert path.read_bytes() == before


def test_corrupt_profile_has_a_clear_error_and_missing_profile_is_optional(tmp_path):
    assert load_profile(tmp_path, "default") is None
    (tmp_path / "default.json").write_text(json.dumps({"name": "default"}))
    with pytest.raises(ValueError, match="Invalid calibration"):
        load_profile(tmp_path, "default")


def test_synthetic_calibration_is_marked_as_demo():
    wizard = CalibrationWizard(CounterConfig(), "demo", "standard", "synthetic demo")
    hold(wizard, 0, 172)
    assert hold(wizard, 3, 82).profile.source == "synthetic demo"
