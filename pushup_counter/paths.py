"""Writable personal data lives outside the source/executable installation folder."""

import os
import sys
from pathlib import Path


def data_directory() -> Path:
    override = os.environ.get("PUSHUP_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        return (
            Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
            / "PushUpCounter"
        )
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "PushUpCounter"
    return (
        Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "pushup-counter"
    )


def workout_directories(primary: Path | None = None) -> list[Path]:
    """Also read version-one logs without moving or changing them."""
    choices = [primary or data_directory() / "workouts", Path.cwd() / "workouts"]
    return list(dict.fromkeys(path.expanduser().resolve() for path in choices))
