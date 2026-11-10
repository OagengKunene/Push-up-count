import csv
import hashlib
import io
import json

import pytest

from pushup_counter import model
from pushup_counter.config import CounterConfig
from pushup_counter.counter import RepEvent
from pushup_counter.storage import WorkoutLog


def test_workout_records_sets_and_totals_without_losing_previous_sets(tmp_path):
    log = WorkoutLog(tmp_path, CounterConfig(), "synthetic demo", "standard")
    log.record(RepEvent(1, 2, 1.2, 85, True, "full rep"))
    log.new_set()
    log.record(RepEvent(0, 4, 0.9, 125, False, "incomplete depth"))
    log.record(RepEvent(1, 6, 1.4, 80, True, "full rep"))
    log.close(8)
    log.close(9)
    summary = json.loads(log.summary_path.read_text())
    assert summary["accepted_reps"] == 2
    assert summary["rejected_attempts"] == 1
    assert summary["sets"] == 2
    assert summary["mean_rep_seconds"] == 1.3
    with log.csv_path.open() as handle:
        assert [row["set"] for row in csv.DictReader(handle)] == ["1", "2", "2"]


def test_offline_missing_or_corrupt_model_has_actionable_error(tmp_path):
    path = tmp_path / "pose.task"
    with pytest.raises(ValueError, match="download-model"):
        model.ensure_model(path, allow_download=False)
    path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        model.ensure_model(path, allow_download=False)


def test_verified_download_is_cached_and_reused(tmp_path, monkeypatch):
    data = b"pretend versioned model"
    monkeypatch.setattr(model, "MODEL_SHA256", hashlib.sha256(data).hexdigest())
    calls = []

    def fetch(*args, **kwargs):
        calls.append(args)
        return io.BytesIO(data)

    monkeypatch.setattr(model.urllib.request, "urlopen", fetch)
    target = tmp_path / "cache" / "pose.task"
    assert model.ensure_model(target).read_bytes() == data
    assert model.ensure_model(target, allow_download=False) == target
    assert len(calls) == 1


def test_bad_download_does_not_replace_existing_file_or_leave_temporary_file(tmp_path, monkeypatch):
    target = tmp_path / "pose.task"
    target.write_bytes(b"existing")
    monkeypatch.setattr(model.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b"bad"))
    with pytest.raises(ValueError, match="checksum"):
        model.ensure_model(target)
    assert target.read_bytes() == b"existing"
    assert list(tmp_path.glob("*.tmp")) == []
