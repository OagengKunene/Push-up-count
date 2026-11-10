"""Offline speech on a bounded worker queue; speaking never blocks camera inference."""

import base64
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable

from .counter import Phase, Snapshot
from .tempo import TempoTarget

WINDOWS_SCRIPT = r"""+$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    if ($env:PUSHUP_VOICE_TEST -eq '1') {
        $synth.SetOutputToNull()
        $synth.Speak('Push up counter voice check')
        [Console]::WriteLine('READY')
        exit 0
    }
    $synth.SetOutputToDefaultAudioDevice()
    $synth.Rate = 1
    [Console]::WriteLine('READY')
    while ($null -ne ($line = [Console]::ReadLine())) {
        if ($line -eq '__QUIT__') { break }
        $synth.Speak($line)
        [Console]::WriteLine('DONE')
    }
} finally { $synth.Dispose() }
"""


def windows_command() -> list[str]:
    encoded = base64.b64encode(WINDOWS_SCRIPT.encode("utf-16-le")).decode("ascii")
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]


def check_voice() -> bool:
    if sys.platform == "win32":
        env = {**os.environ, "PUSHUP_VOICE_TEST": "1"}
        result = subprocess.run(
            windows_command(),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return result.returncode == 0 and "READY" in result.stdout
    return bool(
        shutil.which("say")
        if sys.platform == "darwin"
        else (shutil.which("espeak-ng") or shutil.which("espeak"))
    )


class SystemVoice:
    def __init__(self):
        self.process: subprocess.Popen | None = None
        self.executable = None
        if sys.platform == "win32":
            self.process = subprocess.Popen(
                windows_command(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if self.process.stdout.readline().strip() != "READY":
                self.close()
                raise RuntimeError("Windows speech engine or audio output is unavailable")
        else:
            self.executable = (
                shutil.which("say")
                if sys.platform == "darwin"
                else (shutil.which("espeak-ng") or shutil.which("espeak"))
            )
            if not self.executable:
                raise RuntimeError("Install espeak-ng to enable offline speech on Linux")

    def speak(self, phrase: str) -> None:
        if self.process:
            self.process.stdin.write(phrase.replace("\n", " ") + "\n")
            self.process.stdin.flush()
            if self.process.stdout.readline().strip() != "DONE":
                raise RuntimeError("Speech engine stopped")
        else:
            subprocess.run(
                [self.executable, phrase],
                check=True,
                timeout=15,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    def close(self) -> None:
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.process.kill()
            for stream in (self.process.stdin, self.process.stdout):
                if stream:
                    stream.close()


class Speaker:
    def __init__(self, enabled: bool = False, backend_factory: Callable = SystemVoice):
        self.enabled = enabled
        self.error: str | None = None
        self._queue: queue.Queue = queue.Queue(maxsize=3)
        self._stop = threading.Event()
        self._backend_factory = backend_factory
        self._backend = None
        self._thread = None
        if enabled:
            self._thread = threading.Thread(target=self._work, daemon=True, name="offline-voice")
            self._thread.start()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if enabled and self._thread is None and not self._stop.is_set():
            self._thread = threading.Thread(target=self._work, daemon=True, name="offline-voice")
            self._thread.start()
        if not enabled:
            while True:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break

    def say(self, phrase: str, *, important: bool = False) -> None:
        if not self.enabled or self.error or self._stop.is_set():
            return
        if important:
            while True:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
        try:
            self._queue.put_nowait((time.monotonic(), phrase[:180]))
        except queue.Full:
            pass

    def _work(self) -> None:
        try:
            self._backend = self._backend_factory()
            while not self._stop.is_set():
                try:
                    created, phrase = self._queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                if self.enabled and time.monotonic() - created < 4:
                    self._backend.speak(phrase)
        except Exception as exc:
            if not self._stop.is_set():
                self.error = str(exc)
                print(json.dumps({"voice_unavailable": self.error}), file=sys.stderr)
        finally:
            if self._backend:
                self._backend.close()

    def close(self) -> None:
        self._stop.set()
        if self._backend:
            self._backend.close()
        if self._thread:
            self._thread.join(timeout=1)


class VoiceCoach:
    def __init__(self, speaker: Speaker, tempo: TempoTarget | None = None):
        self.speaker, self.tempo = speaker, tempo
        self.previous: Phase | None = None
        self.last_feedback = ""
        self.last_feedback_at = -100.0

    def update(self, timestamp: float, snapshot: Snapshot) -> None:
        if snapshot.event:
            event = snapshot.event
            phrase = f"Rep {event.number}" if event.accepted else event.reason
            if event.accepted and self.tempo and event.tempo_match is False:
                phrase += ". " + self.tempo.feedback(
                    event.lowering_seconds, event.bottom_seconds, event.rising_seconds
                )
            self.speaker.say(phrase, important=True)
        elif snapshot.phase != self.previous:
            cues = {
                Phase.TOP: "Ready",
                Phase.LOWERING: f"Lower over {self.tempo.lowering:g} seconds"
                if self.tempo
                else "Lower",
                Phase.BOTTOM: f"Hold {self.tempo.bottom:g} seconds"
                if self.tempo and (self.tempo.bottom > 0)
                else "Push up",
                Phase.RISING: "Push up",
            }
            if snapshot.phase in cues:
                self.speaker.say(cues[snapshot.phase])
        elif snapshot.phase == Phase.SEEKING_TOP and timestamp - self.last_feedback_at >= 8:
            if snapshot.feedback != self.last_feedback or timestamp - self.last_feedback_at >= 20:
                self.speaker.say(snapshot.feedback)
                self.last_feedback = snapshot.feedback
                self.last_feedback_at = timestamp
        self.previous = snapshot.phase
