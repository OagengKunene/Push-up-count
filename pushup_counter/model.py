"""Download Google's versioned Lite model once, with an integrity check and atomic cache."""

import hashlib
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
)
MODEL_SHA256 = "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a"


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def default_model_path() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".cache"))
    return root / "pushup-counter" / "pose_landmarker_lite.task"


def ensure_model(path: Path | None = None, *, allow_download: bool = True) -> Path:
    target = (path or default_model_path()).expanduser().resolve()
    if target.is_file() and digest(target) == MODEL_SHA256:
        return target
    if not allow_download:
        raise ValueError(f"Model missing or checksum mismatch: {target}. Run --download-model.")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            with urllib.request.urlopen(MODEL_URL, timeout=45) as response:
                size = 0
                while block := response.read(1024 * 1024):
                    size += len(block)
                    if size > 15 * 1024 * 1024:
                        raise ValueError("Model download is unexpectedly large.")
                    handle.write(block)
        if digest(temporary) != MODEL_SHA256:
            raise ValueError("Model checksum mismatch. Retry the download on a trusted connection.")
        temporary.replace(target)
    except (OSError, urllib.error.URLError) as exc:
        raise RuntimeError(
            "Cannot download the pose model. Check your connection, then run --download-model. "
            "For offline use, copy the official model and pass --model PATH. "
            f"Details: {exc}"
        ) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target
