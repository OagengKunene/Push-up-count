"""Camera-based calibration uses the same pose/body checks as workout counting."""

import math
import os
import sys
import time

from .calibration import CalibrationWizard, save_profile
from .config import CounterConfig
from .counter import Phase, Snapshot


def run_calibration(args, config: CounterConfig) -> int:
    import cv2

    from .app import open_camera
    from .demo import demo_frame
    from .model import ensure_model
    from .overlay import draw_dashboard
    from .pose import PoseTracker
    from .voice import Speaker

    wizard = CalibrationWizard(
        config,
        args.profile,
        args.variant,
        "synthetic demo" if args.demo else "video" if args.video else "webcam",
    )
    capture = tracker = None
    speaker = Speaker(args.voice)
    count, success, last_stage = 0, False, ""
    try:
        if not args.demo:
            model = ensure_model(args.model, allow_download=not args.offline)
            tracker = PoseTracker(model, config, args.variant, args.side)
            capture = cv2.VideoCapture(str(args.video)) if args.video else open_camera(args.camera)
            if not capture.isOpened():
                raise RuntimeError("Cannot open the camera/video for calibration.")
        fps = capture.get(cv2.CAP_PROP_FPS) if capture is not None else 30.0
        if not math.isfinite(fps) or not 0 < fps <= 240:
            fps = 30.0
        if not args.headless:
            if sys.platform.startswith("linux") and not (
                os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
            ):
                raise RuntimeError("Calibration needs a desktop, or --headless with a demo/video.")
            cv2.namedWindow("Push-up Calibration", cv2.WINDOW_NORMAL)
        started = time.perf_counter()
        while not args.max_frames or count < args.max_frames:
            if args.stop_file and args.stop_file.exists():
                break
            elapsed = count / fps if (args.video or args.demo) else time.perf_counter() - started
            if args.demo:
                frame, pose = demo_frame(elapsed, 172 if elapsed < 3 else 82)
            else:
                ok, frame = capture.read()
                if not ok:
                    break
                scale = min(960 / frame.shape[1], 720 / frame.shape[0], 1.0)
                if scale < 1:
                    frame = cv2.resize(
                        frame, (int(frame.shape[1] * scale), int(frame.shape[0] * scale))
                    )
                mirror = args.mirror if args.mirror is not None else not args.video
                if mirror:
                    frame = cv2.flip(frame, 1)
                pose = tracker.process(frame, elapsed)
            status = wizard.update(elapsed, pose.observation)
            count += 1
            if status.stage != last_stage:
                speaker.say(status.prompt, important=True)
                last_stage = status.stage
            if status.profile:
                target = save_profile(args.profile_dir, status.profile)
                print(f"Calibration saved: {target}")
                print(
                    f"Top threshold {status.profile.up_angle:.1f}; "
                    f"bottom threshold {status.profile.down_angle:.1f}"
                )
                success = True
                break
            if not args.headless:
                angle = pose.observation.elbow_angle if pose.observation else None
                snapshot = Snapshot(0, 0, Phase.SEEKING_TOP, angle, status.progress, status.prompt)
                view = draw_dashboard(
                    frame,
                    pose,
                    snapshot,
                    elapsed=elapsed,
                    fps=fps,
                    goal=0,
                    paused=False,
                    variant=args.variant,
                    demo=args.demo,
                    calibration_stage="CAL " + status.stage,
                )
                cv2.imshow("Push-up Calibration", view)
                delay = max(1, int(1000 / fps)) if args.demo or args.video else 1
                key = cv2.waitKey(delay) & 0xFF
                if (
                    key in (ord("q"), 27)
                    or cv2.getWindowProperty("Push-up Calibration", cv2.WND_PROP_VISIBLE) < 1
                ):
                    break
        if not success:
            print("Calibration incomplete; the existing profile was kept.")
        return 0 if success else 2
    finally:
        speaker.close()
        if capture:
            capture.release()
        if tracker:
            tracker.close()
        if not args.headless:
            cv2.destroyAllWindows()
