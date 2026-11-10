"""Command line and resource-safe webcam/video processing loop."""

import argparse
import importlib
import importlib.metadata
import json
import math
import os
import platform
import sys
import time
from pathlib import Path

from . import __version__
from .config import CounterConfig
from .counter import PushUpCounter
from .tempo import TempoTarget


def positive_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Enter a positive finite number.")
    return number


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("Enter an integer greater than zero.")
    return number


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Local webcam push-up counter: OpenCV + MediaPipe")
    result.add_argument("--version", action="version", version=__version__)
    source = result.add_mutually_exclusive_group()
    source.add_argument("--camera", type=int, default=0, help="webcam index (default: 0)")
    source.add_argument("--video", type=Path, help="analyze a local video instead of a webcam")
    source.add_argument("--demo", action="store_true", help="synthetic UI demo; no camera/model")
    result.add_argument("--demo-seconds", type=positive_float, default=12.0)
    result.add_argument("--variant", choices=("standard", "knee"), default="standard")
    result.add_argument("--side", choices=("auto", "left", "right"), default="auto")
    result.add_argument("--up-angle", type=float)
    result.add_argument("--down-angle", type=float)
    result.add_argument("--min-body-angle", type=float, default=155.0)
    result.add_argument("--goal", type=positive_int, help="show a target rep count")
    result.add_argument("--mirror", action=argparse.BooleanOptionalAction, default=None)
    result.add_argument("--sound", action="store_true", help="play a system sound on counted reps")
    result.add_argument("--voice", action="store_true", help="offline spoken counts and coaching")
    result.add_argument(
        "--check-voice", action="store_true", help="check the offline speech engine"
    )
    result.add_argument(
        "--tempo", type=TempoTarget.parse, help="lower-hold-rise seconds, e.g. 3-1-1"
    )
    result.add_argument(
        "--calibrate", action="store_true", help="save guided top/bottom calibration"
    )
    result.add_argument("--profile", default="default", help="calibration profile name")
    result.add_argument("--profile-dir", type=Path)
    result.add_argument("--data-dir", type=Path, help="override the personal data folder")
    result.add_argument("--dashboard", action="store_true", help="open local workout history")
    result.add_argument("--dashboard-output", type=Path)
    result.add_argument(
        "--no-open", action="store_true", help="save the dashboard without opening it"
    )
    result.add_argument("--desktop", action="store_true", help="open the desktop launcher")
    result.add_argument("--stop-file", type=Path, help=argparse.SUPPRESS)
    result.add_argument("--headless", action="store_true", help="skip the preview window")
    result.add_argument("--max-frames", type=positive_int, help="stop after this many frames")
    result.add_argument(
        "--output-video", type=Path, help="explicitly save annotated video (.mp4/.avi)"
    )
    result.add_argument("--log-dir", type=Path)
    result.add_argument("--no-log", action="store_true", help="disable CSV/JSON workout files")
    result.add_argument("--model", type=Path, help="path to the official Lite v1 model")
    result.add_argument("--offline", action="store_true", help="never download a missing model")
    result.add_argument("--download-model", action="store_true", help="cache the model, then exit")
    result.add_argument("--check", action="store_true", help="check imports and cached model")
    result.add_argument("--debug", action="store_true", help="show a traceback if an error occurs")
    result.add_argument(
        "--check-camera", action="store_true", help="read one webcam frame, then exit"
    )
    return result


def diagnostics(check_camera: bool, camera: int, model: Path | None) -> int:
    from .model import MODEL_SHA256, default_model_path, digest

    print(f"Python {platform.python_version()} / {platform.system()} / {platform.machine()}")
    ok = True
    for module, package in (
        ("cv2", "opencv-contrib-python"),
        ("mediapipe", "mediapipe"),
        ("numpy", "numpy"),
    ):
        try:
            importlib.import_module(module)
            print(f"[OK] {package} {importlib.metadata.version(package)}")
        except (ImportError, OSError) as exc:
            print(f"[FAIL] {package}: {exc}")
            ok = False
    target = model or default_model_path()
    valid = target.is_file() and digest(target) == MODEL_SHA256
    print(f"Model: {'verified' if valid else 'not cached / invalid (run --download-model)'}")
    if check_camera and ok:
        capture = open_camera(camera)
        try:
            success, _ = capture.read()
            print("[OK] Camera frame received" if success else "[FAIL] Camera cannot supply frames")
            ok = ok and success
        finally:
            capture.release()
    return 0 if ok else 1


def open_camera(index: int):
    import cv2

    # Prefer DirectShow on Windows, with the platform default as a fallback.
    capture = cv2.VideoCapture(index, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(index)
    if not capture.isOpened() and os.name == "nt":
        capture.release()
        capture = cv2.VideoCapture(index)
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    return capture


def notify_rep() -> None:
    if os.name == "nt":
        import winsound

        winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
    else:
        print("\a", end="", flush=True)


def run(args: argparse.Namespace, config: CounterConfig) -> int:
    import cv2

    from .demo import demo_frame
    from .model import ensure_model
    from .overlay import draw_dashboard
    from .pose import PoseTracker
    from .storage import WorkoutLog
    from .voice import Speaker, VoiceCoach

    counter = PushUpCounter(config, args.tempo)
    speaker = Speaker(args.voice)
    coach = VoiceCoach(speaker, args.tempo)
    capture = tracker = writer = log = None
    processed, elapsed, end_reason = 0, 0.0, "finished"
    mirror = args.mirror if args.mirror is not None else not (args.video or args.demo)
    paused = False
    try:
        if not args.demo:
            if args.video and not args.video.is_file():
                raise ValueError(f"Video not found: {args.video}")
            model = ensure_model(args.model, allow_download=not args.offline)
            tracker = PoseTracker(model, config, args.variant, args.side)
            capture = cv2.VideoCapture(str(args.video)) if args.video else open_camera(args.camera)
            if not capture.isOpened():
                raise RuntimeError(
                    "Cannot open video/camera. Close other camera apps, check Camera privacy "
                    "permissions, or try --camera 1."
                )
        fps = capture.get(cv2.CAP_PROP_FPS) if capture is not None else 30.0
        if not math.isfinite(fps) or fps <= 0 or fps > 240:
            fps = 30.0
        if not args.no_log:
            source = "synthetic demo" if args.demo else ("video" if args.video else "webcam")
            log = WorkoutLog(args.log_dir, config, source, args.variant)
            log.metadata.update(
                {"profile": args.profile, "target_tempo": str(args.tempo) if args.tempo else None}
            )
        if not args.headless:
            if sys.platform.startswith("linux") and not (
                os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
            ):
                raise RuntimeError("No desktop display found. Use --headless for video/demo input.")
            cv2.namedWindow("Push-up Counter", cv2.WINDOW_NORMAL)
        started = time.perf_counter()
        previous = started
        smoothed_fps = 0.0
        while True:
            if args.stop_file and args.stop_file.exists():
                end_reason = "user finished"
                break
            if args.max_frames and processed >= args.max_frames:
                break
            elapsed = (
                processed / fps if (args.video or args.demo) else time.perf_counter() - started
            )
            if args.demo and elapsed >= args.demo_seconds:
                break
            if not paused:
                if args.demo:
                    frame, pose = demo_frame(elapsed)
                else:
                    success, frame = capture.read()
                    if not success:
                        if args.video:
                            end_reason = "end of video"
                            break
                        raise RuntimeError(
                            "Webcam stopped delivering frames. Reconnect it and retry."
                        )
                    scale = min(960 / frame.shape[1], 720 / frame.shape[0], 1.0)
                    if scale < 1:
                        frame = cv2.resize(
                            frame, (int(frame.shape[1] * scale), int(frame.shape[0] * scale))
                        )
                    if mirror:
                        frame = cv2.flip(frame, 1)
                    pose = tracker.process(frame, elapsed)
                snapshot = counter.update(elapsed, pose.observation)
                coach.update(elapsed, snapshot)
                if snapshot.event:
                    if log:
                        log.record(snapshot.event)
                    if snapshot.event.accepted:
                        print(
                            f"Rep {counter.reps} | {snapshot.event.duration:.2f}s | "
                            f"depth {snapshot.event.min_angle:.0f} deg",
                            flush=True,
                        )
                        if args.sound:
                            notify_rep()
                processed += 1
                now = time.perf_counter()
                instantaneous = 1 / max(now - previous, 1e-6)
                smoothed_fps = (
                    instantaneous
                    if not smoothed_fps
                    else (0.1 * instantaneous + 0.9 * smoothed_fps)
                )
                previous = now
            display = draw_dashboard(
                frame,
                pose,
                snapshot,
                elapsed=elapsed,
                fps=smoothed_fps,
                goal=args.goal or 0,
                paused=paused,
                variant=args.variant,
                demo=args.demo,
                tempo=args.tempo,
                voice_status="unavailable"
                if speaker.error
                else ("on" if speaker.enabled else "off"),
            )
            if args.output_video and not paused:
                if writer is None:
                    args.output_video.parent.mkdir(parents=True, exist_ok=True)
                    codec = "mp4v" if args.output_video.suffix.lower() == ".mp4" else "MJPG"
                    writer = cv2.VideoWriter(
                        str(args.output_video),
                        cv2.VideoWriter_fourcc(*codec),
                        fps,
                        (display.shape[1], display.shape[0]),
                    )
                    if not writer.isOpened():
                        raise RuntimeError("Cannot create output video. Try an .avi output path.")
                writer.write(display)
            if not args.headless:
                cv2.imshow("Push-up Counter", display)
                delay = max(1, int(1000 / fps)) if args.demo or args.video else 1
                key = cv2.waitKey(delay) & 0xFF
                if key in (ord("q"), ord("Q"), 27):
                    end_reason = "user quit"
                    break
                if key == ord(" "):
                    paused = not paused
                    counter.interrupt()
                    snapshot = counter.snapshot("Return to a straight-arm plank")
                if key in (ord("r"), ord("R")):
                    counter.reset()
                    snapshot = counter.snapshot("New set - start in a straight-arm plank")
                    if log:
                        log.new_set()
                if key in (ord("m"), ord("M")):
                    mirror = not mirror
                    counter.interrupt()
                    snapshot = counter.snapshot("View changed - start in a straight-arm plank")
                if key in (ord("v"), ord("V")):
                    speaker.set_enabled(not speaker.enabled)
                if key in (ord("d"), ord("D")):
                    from .history import generate_dashboard

                    generate_dashboard([args.log_dir], open_browser=True)
                if cv2.getWindowProperty("Push-up Counter", cv2.WND_PROP_VISIBLE) < 1:
                    end_reason = "window closed"
                    break
        return 0
    except KeyboardInterrupt:
        end_reason = "interrupted"
        return 0
    except Exception:
        end_reason = "error"
        raise
    finally:
        speaker.close()
        if capture is not None:
            capture.release()
        if writer is not None:
            writer.release()
        if tracker is not None:
            tracker.close()
        if not args.headless:
            cv2.destroyAllWindows()
        if log is not None:
            log.metadata["processed_frames"] = processed
            log.close(elapsed, end_reason)
            print(f"Workout summary: {log.summary_path}")
        print(
            json.dumps(
                {
                    "reps_in_current_set": counter.reps,
                    "rejected": counter.rejected,
                    "processed_frames": processed,
                    "end_reason": end_reason,
                }
            )
        )


def main(argv: list[str] | None = None) -> int:
    cli = parser()
    args = cli.parse_args(argv)
    if args.camera < 0:
        cli.error("--camera must be non-negative")
    if args.headless and not (
        args.video
        or args.demo
        or args.max_frames
        or args.check
        or args.dashboard
        or args.download_model
        or args.check_voice
    ):
        cli.error("Headless webcam use requires --max-frames so the run stops automatically.")
    if args.output_video:
        if args.output_video.suffix.lower() not in (".mp4", ".avi"):
            cli.error("--output-video must end in .mp4 or .avi")
        if args.output_video.exists():
            cli.error("Output video already exists; choose a new name.")
        if args.video and args.video.resolve() == args.output_video.resolve():
            cli.error("Input and output video paths must differ.")
    try:
        from dataclasses import replace

        from .calibration import load_profile, profile_filename
        from .paths import data_directory

        if args.data_dir:
            os.environ["PUSHUP_DATA_DIR"] = str(args.data_dir.expanduser().resolve())
        args.log_dir = args.log_dir or data_directory() / "workouts"
        args.profile_dir = args.profile_dir or data_directory() / "profiles"
        profile_filename(args.profile)
        if args.desktop:
            from .desktop import launch

            return launch()
        if args.dashboard:
            from .history import generate_dashboard

            print(
                generate_dashboard(
                    [args.log_dir], args.dashboard_output, open_browser=not args.no_open
                )
            )
            return 0
        if args.check_voice:
            from .voice import check_voice

            available = check_voice()
            print("Offline speech engine ready" if available else "Offline speech unavailable")
            return 0 if available else 1
        config = CounterConfig(min_body_angle=args.min_body_angle)
        profile = load_profile(args.profile_dir, args.profile) if not args.calibrate else None
        if profile:
            if profile.source == "synthetic demo" and not args.demo:
                raise ValueError("This is a demo calibration; recalibrate with your camera first.")
            if profile.variant != args.variant:
                raise ValueError(
                    "Profile variant differs; choose the matching variant or recalibrate."
                )
            config = profile.apply(config)
        if args.up_angle is not None:
            config = replace(config, up_angle=args.up_angle)
        if args.down_angle is not None:
            config = replace(config, down_angle=args.down_angle)
        if args.check or args.check_camera:
            return diagnostics(args.check_camera, args.camera, args.model)
        if args.download_model:
            from .model import ensure_model

            print(f"Model ready: {ensure_model(args.model, allow_download=not args.offline)}")
            return 0
        if args.calibrate:
            from .calibration_ui import run_calibration

            return run_calibration(args, config)
        return run(args, config)
    except Exception as exc:
        if args.debug:
            raise
        print(f"Error: {exc}", file=sys.stderr)
        print(
            "Use python app.py --check for diagnostics; see README.md for setup.", file=sys.stderr
        )
        return 1
