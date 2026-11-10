import json

from pushup_counter.config import CounterConfig
from pushup_counter.counter import RepEvent
from pushup_counter.history import generate_dashboard, load_history
from pushup_counter.storage import WorkoutLog


def test_old_and_new_logs_are_read_without_modification(tmp_path):
    log = WorkoutLog(tmp_path, CounterConfig(), "webcam", "standard")
    log.record(RepEvent(1, 2, 1.2, 85, True, "full rep", 0.4, 0.3, 0.5, 94, 174, 170, True))
    log.close(10)
    old = {
        "started_utc": "2026-01-01T10:00:00+00:00",
        "source": "webcam",
        "variant": "knee",
        "accepted_reps": 5,
        "sets": 1,
        "elapsed_seconds": 20,
        "rep_csv": "missing.csv",
    }
    old_path = tmp_path / "old_summary.json"
    old_path.write_text(json.dumps(old))
    before = old_path.read_bytes()
    history = load_history([tmp_path, tmp_path])
    assert len(history["sessions"]) == 2
    assert history["sessions"][0]["events"][0]["quality_score"] == 94
    assert old_path.read_bytes() == before


def test_demo_is_identified_and_corrupt_summaries_are_skipped(tmp_path):
    log = WorkoutLog(tmp_path, CounterConfig(), "synthetic demo", "standard")
    log.close(5)
    (tmp_path / "bad_summary.json").write_text("broken")
    result = load_history([tmp_path])
    assert result["sessions"][0]["demo"] is True
    assert result["skipped"] == 1


def test_html_payload_cannot_break_out_of_script_and_report_needs_no_network(tmp_path):
    log = WorkoutLog(
        tmp_path, CounterConfig(), '</script><script>alert("injected")</script>', "standard"
    )
    log.close(5)
    report = generate_dashboard([tmp_path], tmp_path / "report.html", open_browser=False)
    html = report.read_text(encoding="utf-8")
    assert "\\u003c/script>" in html
    assert '<script>alert("injected")</script>' not in html
    assert "__WORKOUT_DATA__" not in html
    assert "https://" not in html


def test_rep_csv_cannot_read_outside_the_workout_directory(tmp_path):
    log = WorkoutLog(tmp_path, CounterConfig(), "webcam", "standard")
    log.close(5)
    summary = json.loads(log.summary_path.read_text())
    summary["rep_csv"] = "../secret.csv"
    log.summary_path.write_text(json.dumps(summary))
    assert load_history([tmp_path])["sessions"][0]["events"] == []
