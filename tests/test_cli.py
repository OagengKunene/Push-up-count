import pytest

from pushup_counter.app import main


@pytest.mark.parametrize(
    "args",
    [
        ["--demo", "--demo-seconds", "nan"],
        ["--goal", "0"],
        ["--camera", "-1"],
        ["--headless"],
        ["--output-video", "test.txt"],
    ],
)
def test_invalid_cli_arguments_fail_before_opening_camera(args):
    with pytest.raises(SystemExit) as result:
        main(args)
    assert result.value.code == 2


def test_invalid_thresholds_report_clear_error(capsys):
    assert main(["--up-angle", "50"]) == 1
    assert "down angle < up angle" in capsys.readouterr().err


def test_native_library_errors_are_reported_without_a_traceback(monkeypatch, capsys):
    from pushup_counter import app

    class NativeVideoError(Exception):
        pass

    def fail(*args):
        raise NativeVideoError("Video driver unavailable")

    monkeypatch.setattr(app, "run", fail)
    assert main(["--demo"]) == 1
    assert "Video driver unavailable" in capsys.readouterr().err
