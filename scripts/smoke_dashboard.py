"""Browser-level regression checks and an explicitly synthetic dashboard preview."""

import argparse
import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

from pushup_counter.config import CounterConfig
from pushup_counter.counter import RepEvent
from pushup_counter.history import generate_dashboard
from pushup_counter.storage import WorkoutLog


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("verification/dashboard.png"))
    parser.add_argument("--browser", help="optional path to an installed Chromium executable")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pushup-dashboard-") as directory:
        folder = Path(directory)
        for index, reps in enumerate([12, 18, 15, 24, 20, 8]):
            log = WorkoutLog(
                folder, CounterConfig(), "synthetic demo", "knee" if index == 5 else "standard"
            )
            for rep in range(1, reps + 1):
                log.record(
                    RepEvent(
                        rep,
                        rep * 3.2,
                        2.1,
                        86,
                        True,
                        "full rep",
                        0.85,
                        0.35,
                        0.9,
                        90 + index,
                        171,
                        169,
                        index % 2 == 0,
                    )
                )
            log.metadata["target_tempo"] = "1-0-1"
            log.close(reps * 3.2)
            summary = json.loads(log.summary_path.read_text())
            summary["started_utc"] = (datetime.now(UTC) - timedelta(days=5 - index)).isoformat()
            log.summary_path.write_text(json.dumps(summary))
        report = generate_dashboard([folder], folder / "report.html", open_browser=False)
        with sync_playwright() as playwright:
            options = {"executable_path": args.browser} if args.browser else {}
            browser = playwright.chromium.launch(headless=True, **options)
            page = browser.new_page(viewport={"width": 1440, "height": 1050}, device_scale_factor=1)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(report.as_uri())
            assert page.locator("#total").inner_text() == "0"
            page.locator("#demos").check()
            assert page.locator("#total").inner_text() == "97"
            assert page.locator("#best").inner_text() == "24"
            assert page.locator("#active").inner_text() == "6 / 7"
            page.locator("#variant").select_option("knee")
            assert page.locator("#total").inner_text() == "8"
            page.locator("#variant").select_option("all")
            page.locator("#sessions .view").first.click()
            assert page.locator("#details").is_visible()
            assert page.locator("#repRows tr").count() == 8
            page.locator("#closeDetails").click()
            with page.expect_download() as download:
                page.locator("#export").click()
            csv_path = folder / "history.csv"
            download.value.save_as(csv_path)
            assert csv_path.read_text().count("\n") == 6
            page.locator("#weeklyGoal").fill("150")
            assert "/ 150 reps" in page.locator("#goalOf").inner_text()
            page.screenshot(path=str(args.output), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth") <= 390
            page.screenshot(
                path=str(args.output.with_stem(args.output.stem + "_mobile")), full_page=True
            )
            assert not errors, errors
            browser.close()
        print("Dashboard checks passed: filters, totals, rep details, export and mobile layout.")


if __name__ == "__main__":
    main()
