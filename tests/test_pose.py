import math
from types import SimpleNamespace

import pytest

from pushup_counter.config import CounterConfig
from pushup_counter.geometry import angle, horizontal_tilt
from pushup_counter.pose import SIDES, PoseAnalyzer


def landmarks(side="left"):
    result = [SimpleNamespace(x=0.5, y=0.5, visibility=0.0, presence=1.0) for _ in range(33)]
    coords = [(0.2, 0.35), (0.2, 0.55), (0.2, 0.75), (0.5, 0.36), (0.7, 0.36), (0.9, 0.36)]
    for i, (x, y) in zip(SIDES[side], coords, strict=True):
        result[i] = SimpleNamespace(x=x, y=y, visibility=0.98, presence=0.99)
    return result


def test_geometry_known_angles_and_degenerate_points():
    assert angle((0, 0), (1, 0), (2, 0)) == pytest.approx(180)
    assert angle((0, 0), (1, 0), (1, 1)) == pytest.approx(90)
    assert angle((1, 0), (1, 0), (2, 0)) is None
    assert angle((math.nan, 0), (1, 0), (2, 0)) is None
    assert horizontal_tilt((0, 0), (0, 1)) == 90


def test_visible_side_is_selected():
    observation = PoseAnalyzer(CounterConfig()).analyze(landmarks(), 1280, 720)
    assert observation.side == "left"
    assert observation.elbow_angle == pytest.approx(180)
    assert observation.support_ok


def test_wrong_manual_side_returns_no_observation():
    assert PoseAnalyzer(CounterConfig(), side="right").analyze(landmarks(), 1280, 720) is None


def test_cropped_or_invisible_support_point_disables_counting():
    points = landmarks()
    points[27].x = 1.2
    assert PoseAnalyzer(CounterConfig()).analyze(points, 1280, 720) is None
    points[27].x = 0.9
    points[27].visibility = 0.1
    assert PoseAnalyzer(CounterConfig()).analyze(points, 1280, 720) is None


def test_knee_variant_does_not_require_ankle_visibility():
    points = landmarks()
    points[27].visibility = 0
    assert PoseAnalyzer(CounterConfig(), variant="knee").analyze(points, 1280, 720) is not None


def test_aspect_ratio_is_corrected_before_measuring_angle():
    points = landmarks()
    points[11].x, points[11].y = 0.25, 0.25
    points[13].x, points[13].y = 0.5, 0.5
    points[15].x, points[15].y = 0.75, 0.5
    result = PoseAnalyzer(CounterConfig()).analyze(points, 1000, 500)
    assert result.elbow_angle == pytest.approx(153.4349488)


def test_missing_landmarks_and_nonfinite_values():
    analyzer = PoseAnalyzer(CounterConfig())
    assert analyzer.analyze(None, 1280, 720) is None
    assert analyzer.analyze([], 1280, 720) is None
    points = landmarks()
    points[13].x = math.nan
    assert analyzer.analyze(points, 1280, 720) is None
