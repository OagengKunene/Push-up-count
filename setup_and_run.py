"""Create an isolated environment with the user's installed Python, then run the app."""

import hashlib
import os
import platform
import struct
import subprocess
import sys
from pathlib import Path


def main() -> int:
    if not (3, 11) <= sys.version_info[:2] <= (3, 14) or struct.calcsize("P") != 8:
        print("Install 64-bit Python 3.11-3.14 from https://www.python.org/downloads/.")
        print(f"Current interpreter: {platform.python_version()} ({struct.calcsize('P') * 8}-bit)")
        return 1
    root = Path(__file__).resolve().parent
    environment = root / ".venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    marker = environment / ".pushup-setup"
    fingerprint = hashlib.sha256(
        (root / "pyproject.toml").read_bytes() + sys.version.encode()
    ).hexdigest()
    try:
        if not python.exists():
            print("Creating the project's Python environment...", flush=True)
            subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
        if not marker.exists() or marker.read_text() != fingerprint:
            print("Installing dependencies (internet required on first launch)...", flush=True)
            subprocess.run([str(python), "-m", "pip", "install", "--upgrade", "pip"], check=True)
            subprocess.run([str(python), "-m", "pip", "install", "-e", str(root)], check=True)
            marker.write_text(fingerprint)
        entry = (
            ["-m", "pushup_counter", *sys.argv[1:]] if sys.argv[1:] else [str(root / "desktop.py")]
        )
        return subprocess.call([str(python), *entry], cwd=root)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Setup failed: {exc}")
        print("Check your internet connection and the troubleshooting steps in README.md.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
