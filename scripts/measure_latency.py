"""Measure NOVA's real latency on this Mac. Makes real (billable) Gemini API calls.

Spoken questions are generated with macOS `say` as 16 kHz WAV, the same format the
Recorder produces, so runs are repeatable and need no microphone.
"""

import statistics
import subprocess
import tempfile
import time
from pathlib import Path

from nova.ai import AIError, GeminiClient, Message
from nova.config import load_config
from nova.speech import Speaker

QUESTIONS = [
    "What is the capital of Nepal?",
    "How many days are there in a leap year?",
    "Give me one tip for better sleep.",
]
RUNS_PER_QUESTION = 3


def synthesize(text: str, path: Path) -> bytes:
    """Render `text` as speech into a 16 kHz mono WAV file and return its bytes."""
    subprocess.run(
        ["say", "-o", str(path), "--file-format=WAVE", "--data-format=LEI16@16000", text],
        check=True,
    )
    return path.read_bytes()


def main() -> None:
    config = load_config()
    client = GeminiClient(config)
    speaker = Speaker()
    timings: dict[str, list[float]] = {
        "Transcription": [],
        "Model reply": [],
        "Speech start": [],
        "Total (recording end → speech starts)": [],
    }
    failures = 0

    try:
        with tempfile.TemporaryDirectory() as folder:
            audio = {
                question: synthesize(question, Path(folder) / f"q{index}.wav")
                for index, question in enumerate(QUESTIONS)
            }
            for run in range(1, RUNS_PER_QUESTION + 1):
                for question, wav in audio.items():
                    try:
                        start = time.perf_counter()
                        transcript = client.transcribe(wav)
                        transcribed = time.perf_counter()
                        answer = client.reply([Message("user", transcript or question)])
                        answered = time.perf_counter()
                        speaker.speak(answer)
                        speaking = time.perf_counter()
                    except AIError as exc:
                        failures += 1
                        print(f"run {run}: FAILED: {exc}")
                        continue
                    finally:
                        speaker.stop()

                    timings["Transcription"].append(transcribed - start)
                    timings["Model reply"].append(answered - transcribed)
                    timings["Speech start"].append(speaking - answered)
                    timings["Total (recording end → speech starts)"].append(speaking - start)
                    print(f"run {run}: heard {transcript!r} in {speaking - start:.2f}s total")
    finally:
        speaker.stop()
        client.close()

    measured = len(timings["Transcription"])
    print()
    print(f"Model: {config.model} | measured runs: {measured} | failed runs: {failures}")
    print()
    print("| Step | Median | Fastest | Slowest |")
    print("| --- | --- | --- | --- |")
    for step, values in timings.items():
        if values:
            print(
                f"| {step} | {statistics.median(values):.2f} s | "
                f"{min(values):.2f} s | {max(values):.2f} s |"
            )


if __name__ == "__main__":
    main()
