"""Backward-compatible history reader and a self-contained, offline interactive dashboard."""

import csv
import json
import math
import webbrowser
from datetime import datetime
from importlib.resources import files
from pathlib import Path

from .paths import data_directory, workout_directories


def number(value, default=None, maximum=1_000_000_000):
    try:
        result = float(value)
        return result if math.isfinite(result) and 0 <= result <= maximum else default
    except (ValueError, TypeError):
        return default


def read_events(directory: Path, filename: str) -> list[dict]:
    if (
        not isinstance(filename, str)
        or Path(filename).name != filename
        or "/" in filename
        or ("\\" in filename)
    ):
        return []
    path = directory / filename
    try:
        if not path.is_file() or path.stat().st_size > 8_000_000:
            return []
        with path.open(encoding="utf-8", newline="") as handle:
            events = []
            for index, row in enumerate(csv.DictReader(handle)):
                if index >= 20000:
                    break
                timestamp, duration = number(row.get("timestamp")), number(row.get("duration"))
                if timestamp is None or duration is None:
                    continue
                events.append(
                    {
                        "set": int(number(row.get("set"), 1)),
                        "number": int(number(row.get("number"), 0)),
                        "timestamp": timestamp,
                        "duration": duration,
                        "accepted": row.get("accepted", "").lower() == "true",
                        "reason": str(row.get("reason", ""))[:180],
                        "min_angle": number(row.get("min_angle"), maximum=180),
                        "quality_score": number(row.get("quality_score"), maximum=100),
                        "lowering_seconds": number(row.get("lowering_seconds")),
                        "bottom_seconds": number(row.get("bottom_seconds")),
                        "rising_seconds": number(row.get("rising_seconds")),
                        "tempo_match": {"true": True, "false": False}.get(
                            str(row.get("tempo_match", "")).lower()
                        ),
                    }
                )
            return events
    except (OSError, UnicodeError, csv.Error):
        return []


def load_history(directories: list[Path]) -> dict:
    sessions, skipped, seen = [], 0, set()
    for directory in directories:
        directory = directory.expanduser().resolve()
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*_summary.json")):
            if path in seen:
                continue
            seen.add(path)
            try:
                if path.stat().st_size > 64000:
                    raise ValueError("Oversized summary")
                summary = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(summary, dict):
                    raise ValueError("Summary must be an object")
                started = datetime.fromisoformat(summary["started_utc"])
                if started.tzinfo is None:
                    raise ValueError("Summary timestamp must include timezone")
                reps = number(summary.get("accepted_reps"))
                if reps is None or reps != int(reps):
                    raise ValueError("Invalid rep count")
                source = str(summary.get("source", "unknown"))[:60]
                variant = str(summary.get("variant", "standard"))[:30]
                sessions.append(
                    {
                        "id": str(len(sessions)),
                        "started": started.isoformat(),
                        "source": source,
                        "variant": variant,
                        "demo": "demo" in source.lower() or "synthetic" in source.lower(),
                        "reps": int(reps),
                        "retries": int(number(summary.get("rejected_attempts"), 0)),
                        "sets": int(number(summary.get("sets"), 1)),
                        "elapsed": number(summary.get("elapsed_seconds"), 0),
                        "quality": number(summary.get("mean_quality_score"), maximum=100),
                        "tempo_rate": number(summary.get("tempo_match_rate"), maximum=1),
                        "target_tempo": str(summary.get("target_tempo") or "")[:40],
                        "profile": str(summary.get("profile") or "default")[:40],
                        "events": read_events(directory, summary.get("rep_csv", "")),
                    }
                )
            except (OSError, ValueError, TypeError, KeyError, UnicodeError):
                skipped += 1
    sessions.sort(key=lambda row: datetime.fromisoformat(row["started"]).timestamp(), reverse=True)
    return {"sessions": sessions, "skipped": skipped}


def generate_dashboard(
    directories: list[Path] | None = None, output: Path | None = None, *, open_browser: bool = True
) -> Path:
    directories = directories or workout_directories()
    # Keep earlier source-folder logs visible after upgrading to app-data storage.
    directories = list(dict.fromkeys([*directories, *workout_directories(directories[0])]))
    payload = json.dumps(load_history(directories), ensure_ascii=True, allow_nan=False).replace(
        "<", "\\u003c"
    )
    template = (
        files("pushup_counter").joinpath("resources/dashboard.html").read_text(encoding="utf-8")
    )
    html = template.replace("__WORKOUT_DATA__", payload)
    target = (output or data_directory() / "reports" / "dashboard.html").expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(html, encoding="utf-8")
    temporary.replace(target)
    if open_browser:
        webbrowser.open(target.as_uri())
    return target
