import threading

from pushup_counter.counter import Phase, RepEvent, Snapshot
from pushup_counter.voice import Speaker, VoiceCoach


class RecordingSpeaker:
    def __init__(self):
        self.phrases = []

    def say(self, phrase, **kwargs):
        self.phrases.append(phrase)


def test_repeated_form_feedback_is_rate_limited_but_rep_counts_are_announced():
    speaker = RecordingSpeaker()
    coach = VoiceCoach(speaker)
    bad = Snapshot(0, 0, Phase.SEEKING_TOP, None, 0, "Keep your body in view")
    for index in range(50):
        coach.update(index / 30, bad)
    assert speaker.phrases == ["Keep your body in view"]
    event = RepEvent(1, 2, 1, 85, True, "full rep")
    coach.update(2, Snapshot(1, 0, Phase.TOP, 170, 0, "Rep counted", event))
    assert speaker.phrases[-1] == "Rep 1"


def test_slow_speech_runs_off_the_camera_thread_and_queue_stays_bounded():
    entered, release = threading.Event(), threading.Event()

    class Backend:
        def speak(self, phrase):
            entered.set()
            release.wait(timeout=2)

        def close(self):
            release.set()

    speaker = Speaker(True, Backend)
    try:
        speaker.say("Start")
        assert entered.wait(timeout=1)
        for index in range(100):
            speaker.say(f"Cue {index}")
        assert speaker._queue.qsize() <= 3
        speaker.say("Rep 10", important=True)
        assert speaker._queue.qsize() == 1
    finally:
        speaker.close()


def test_missing_voice_backend_degrades_gracefully():
    def fail():
        raise RuntimeError("No voice available")

    speaker = Speaker(True, fail)
    speaker._thread.join(timeout=1)
    assert speaker.error == "No voice available"
    speaker.say("Ignored")
    speaker.close()
