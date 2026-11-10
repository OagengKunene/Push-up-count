"""Build a self-contained Windows folder, bundle the verified model, and create a ZIP."""

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

from pushup_counter import __version__
from pushup_counter.model import ensure_model


def main():
    if sys.platform != "win32":
        raise SystemExit("Build this executable on Windows or use the GitHub Actions Windows job.")
    root = Path(__file__).resolve().parents[1]
    assets = root / "build" / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    model = ensure_model(assets / "pose_landmarker_lite.task")
    from PIL import Image, ImageDraw, ImageFont

    icon = Image.new("RGB", (256, 256), "#112d34")
    draw = ImageDraw.Draw(icon)
    draw.rounded_rectangle((22, 22, 234, 234), radius=48, outline="#7ce0bc", width=11)
    font = ImageFont.truetype("arialbd.ttf", 92)
    draw.text((128, 125), "PU", font=font, fill="#7ce0bc", anchor="mm")
    icon_path = assets / "pushup.ico"
    icon.save(icon_path, format="ICO", sizes=[(32, 32), (48, 48), (128, 128), (256, 256)])
    env = {**os.environ, "MPLBACKEND": "Agg"}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onedir",
            "--windowed",
            "--noupx",
            "--name",
            "PushUpCounter",
            "--specpath",
            str(root / "build"),
            "--workpath",
            str(root / "build" / "pyinstaller"),
            "--distpath",
            str(root / "dist"),
            "--icon",
            str(icon_path),
            "--collect-all",
            "mediapipe",
            "--collect-all",
            "cv2",
            "--collect-data",
            "pushup_counter",
            "--hidden-import",
            "tkinter",
            "--copy-metadata",
            "mediapipe",
            "--copy-metadata",
            "opencv-contrib-python",
            "--copy-metadata",
            "numpy",
            "--exclude-module",
            "pytest",
            "--exclude-module",
            "playwright",
            "--add-data",
            str(model) + os.pathsep + "assets",
            str(root / "desktop.py"),
        ],
        cwd=root,
        env=env,
        check=True,
    )
    bundle = root / "dist" / "PushUpCounter"
    shutil.copy2(root / "LICENSE", bundle / "LICENSE.txt")
    (bundle / "START_HERE.txt").write_text(
        "PUSH / UP 2 — WINDOWS\n\n"
        "Extract the entire ZIP, then double-click PushUpCounter.exe.\n"
        "Keep the _internal folder beside the executable. Python is included.\n"
        "The verified pose model is included; no initial download is required.\n\n"
        "1. Place your camera to the side with your full body in view.\n"
        "2. Calibrate profile: hold the top, then the bottom for two seconds each.\n"
        "3. Choose a tempo (e.g. 3-1-1), enable spoken coaching, and start.\n"
        "4. Press Q in the camera window or Finish and save in the launcher.\n"
        "5. Open Workout history to inspect your progress.\n\n"
        "Personal data: %LOCALAPPDATA%\\PushUpCounter\n"
        "Logs and profiles stay local. Recordings require an explicit CLI option.\n"
        "This executable is unsigned. Verify its checksum and source before running.\n"
        "Source, dependencies and licenses: https://github.com/OagengKunene/Push-up-count\n",
        encoding="utf-8",
    )
    name = f"PushUpCounter-{__version__}-windows-x64"
    archive = Path(
        shutil.make_archive(
            str(root / "dist" / name), "zip", root_dir=root / "dist", base_dir="PushUpCounter"
        )
    )
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    (root / "dist" / "SHA256SUMS.txt").write_text(f"{checksum}  {archive.name}\n", encoding="utf-8")
    print(f"Created {archive} ({archive.stat().st_size / 1024**2:.1f} MiB)")


if __name__ == "__main__":
    main()
