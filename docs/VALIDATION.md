# Validation record

Development checks performed on 10 November 2026.

## Completed checks

| Check | Result |
| --- | --- |
| Behavioral regression suite, Linux / Python 3.12.14 | 82 passed |
| Behavioral regression suite, Linux / Python 3.14.10 | 82 passed |
| Ruff lint and formatting | Passed |
| Installed dependency compatibility | Passed for the two tested Python environments |
| Synthetic 12-second movement trace | 4 counted reps, 0 retries, 360 processed frames |
| Synthetic 6-second trace on Python 3.14 | 2 counted reps, 0 retries, 180 processed frames |
| Real MediaPipe inference on blank frames | Passed; no pose / no reps |
| Real video input with 12 blank frames | 12 frames processed, 0 reps |
| Google's public `pose.jpg` human fixture | All 33 landmarks detected; upright position did not count a rep |
| Official Lite v1 model checksum | Verified against the digest stored in `model.py` |
| CSV and JSON logs across multiple sets | Accepted/retry totals and mean durations verified |
| Dashboard screenshot | Rendered with OpenCV and visually inspected |
| Guided synthetic calibration | Stable holds saved 164° top / 90° bottom thresholds |
| Calibrated workout and target tempo | 2 accepted reps; phase timings and pose scores saved |
| Legacy history compatibility | Old summaries remain readable without modification |
| Speech queue and missing backend handling | Background speech stays bounded; unavailable speech does not stop counting |
| Local history report generation | Passed, including per-rep detail data and safe HTML embedding |

Runtime packages used: MediaPipe 0.10.35, OpenCV contrib 5.0.0.93 and NumPy 2.5.4. The pose library is pinned to the release exercised by the native inference checks. Linux native graphics libraries are needed even when inference uses the CPU; see the README installation instructions.

The public human fixture is from [Google's MediaPipe asset storage](https://storage.googleapis.com/mediapipe-assets/pose.jpg). It was used only for development verification and is not bundled in this repository. Its detection check verifies the inference path; it does not measure push-up counting accuracy.

GitHub Actions is configured to check Windows and Linux on Python 3.11 and 3.14. The Actions page records their results after publication. A workflow definition alone is not evidence that those jobs have passed.

Version 2 also adds a Chromium browser test for report interactions and layout, native Windows launcher/speech checks, and a Windows EXE build. The packaged executable is exercised for desktop startup, guided calibration, demo counting with tempo, actual offline model inference and bundled dashboard resources before release publication. The release includes `BUNDLE_VALIDATION.json` and `SHA256SUMS.txt`. See the corresponding Actions run for the completed results; these packaging checks require the Windows runner.

## Live webcam acceptance procedure

The development environment has no physical webcam attached. Perform this short check on the intended computer:

1. Run `python app.py --check-camera` and confirm a frame is received.
2. Use a level side view with the whole visible side of the body in frame. Hold the top position, then perform five complete push-ups. Confirm that the displayed count matches the five movements.
3. Perform a shallow movement and return to the top. Confirm the rep count does not increase and a retry appears.
4. Pause halfway through a movement, resume, and return to the top. Confirm it does not count an unfinished rep. Move out of view briefly and confirm a longer tracking loss also requires a fresh start.
5. Press R, complete a new set, and quit. Check that the current set reset while the workout JSON retains the accepted-rep total from both sets.

Record camera placement, lighting, exercise variant and threshold values if you compare different runs. Counting quality needs real movement footage from the intended setup; synthetic tests cannot establish a real-world accuracy percentage.

## Reproduce the checks

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python app.py --demo --headless --demo-seconds 12 --no-log
python scripts/smoke_model.py
python scripts/render_demo.py
```
