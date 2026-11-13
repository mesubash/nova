"""Measure transcription accuracy on your own voice: Gemini versus local Whisper.

    python scripts/voice_benchmark.py record    # read each phrase aloud; saved on this Mac
    python scripts/voice_benchmark.py compare   # makes real (billable) Gemini calls

Recordings stay in ~/Library/Application Support/NOVA/voice-samples and are never committed.
`compare` writes docs/transcription-results.md, which contains text only, no audio.
"""

import argparse
import json
import re
import statistics
import sys
import time
from datetime import date
from pathlib import Path

from nova.__main__ import wait_for_enter
from nova.ai import AIError, GeminiClient
from nova.config import Config, load_config
from nova.speech import Recorder, RecordingError
from nova.transcription import LocalTranscriber, TranscriptionError

PHRASES = [
    "What is the capital of Nepal?",
    "How many days are there in a leap year?",
    "How far is Pokhara from Kathmandu?",
    "Give me one tip for better sleep.",
    "What time is it in London right now?",
    "Open Safari.",
    "Open Notes.",
    "Search my files for invoice.",
    "Save a note: buy oat milk and bread.",
    "Show my notes.",
    "Find notes about milk.",
    "Change note two to call my brother on Sunday.",
    "Delete note three.",
    "Explain what a neural network is in simple words.",
    "How do I say thank you in Nepali?",
]
MAX_SECONDS = 15
PAUSE_SECONDS = 4.5  # stays under the free tier's 15 requests per minute
OUTPUT = Path("docs/transcription-results.md")
NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
}  # fmt: skip


def samples_dir(config: Config) -> Path:
    return config.data_dir / "voice-samples"


def words(text: str) -> list[str]:
    """Lowercase, drop punctuation, and write small numbers as digits."""
    cleaned = re.sub(r"[^\w\s']", " ", text.lower())
    return [NUMBER_WORDS.get(word, word) for word in cleaned.split()]


def word_error_rate(expected: str, heard: str) -> float:
    """Word-level edit distance (substitutions + insertions + deletions) / expected words."""
    reference, hypothesis = words(expected), words(heard)
    previous = list(range(len(hypothesis) + 1))
    for i, ref_word in enumerate(reference, start=1):
        current = [i]
        for j, hyp_word in enumerate(hypothesis, start=1):
            current.append(
                min(
                    previous[j] + 1,  # a word was deleted
                    current[j - 1] + 1,  # a word was inserted
                    previous[j - 1] + (ref_word != hyp_word),  # a word was substituted
                )
            )
        previous = current
    return previous[-1] / max(len(reference), 1)


def record(config: Config) -> None:
    folder = samples_dir(config)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    recorder = Recorder(MAX_SECONDS)
    manifest = []
    print("Read each phrase naturally, in your normal voice and speed.\n")
    for index, phrase in enumerate(PHRASES, start=1):
        while True:
            input(
                f'[{index}/{len(PHRASES)}] "{phrase}"\n  Press Enter, read it, then press Enter. '
            )
            try:
                wav = recorder.record(wait_for_enter)
            except RecordingError as exc:
                print(f"  {exc} Let's try that one again.")
                continue
            if input("  Keep this recording? [Y/n] ").strip().lower() not in ("n", "no"):
                break
        path = folder / f"{index:02}.wav"
        path.write_bytes(wav)
        path.chmod(0o600)
        manifest.append({"file": path.name, "text": phrase})
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nSaved {len(manifest)} recordings to {folder}")


def compare(config: Config) -> None:
    folder = samples_dir(config)
    manifest_path = folder / "manifest.json"
    if not manifest_path.exists():
        sys.exit("No recordings yet. Run: python scripts/voice_benchmark.py record")
    samples = [
        (item["text"], (folder / item["file"]).read_bytes())
        for item in json.loads(manifest_path.read_text())
    ]

    client = GeminiClient(config)
    local = LocalTranscriber(config.local_model)
    local_name = f"Local ({config.local_model.split('/')[-1]})"
    backends = {"Gemini": client.transcribe, local_name: local}
    local(samples[0][1])  # untimed warm-up: loads the model

    results: dict[str, list[dict]] = {name: [] for name in backends}
    try:
        for index, (expected, wav) in enumerate(samples, start=1):
            for name, transcribe in backends.items():
                if name == "Gemini" and index > 1:
                    time.sleep(PAUSE_SECONDS)
                start = time.perf_counter()
                try:
                    heard, failed = transcribe(wav), False
                except (AIError, TranscriptionError) as exc:
                    heard, failed = f"[failed: {exc}]", True
                seconds = time.perf_counter() - start
                error = None if failed else word_error_rate(expected, heard)
                results[name].append({"heard": heard, "seconds": seconds, "wer": error})
            print(f"{index:2}/{len(samples)} {expected}")
    finally:
        client.close()

    print()
    write_report(samples, results, config)


def summarise(rows: list[dict]) -> dict:
    measured = [row for row in rows if row["wer"] is not None]
    return {
        "wer": statistics.mean(row["wer"] for row in measured) if measured else float("nan"),
        "exact": sum(row["wer"] == 0 for row in measured),
        "median_seconds": statistics.median(row["seconds"] for row in measured) if measured else 0,
        "failed": len(rows) - len(measured),
    }


def cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def write_report(samples: list[tuple[str, bytes]], results: dict, config: Config) -> None:
    names = list(results)
    summaries = {name: summarise(rows) for name, rows in results.items()}
    lines = [
        "# Transcription accuracy on a real voice",
        "",
        f"Run on {date.today().isoformat()} with `scripts/voice_benchmark.py`: {len(samples)} "
        "phrases read aloud by the developer (MacBook Air M4, built-in microphone), each "
        "transcribed by both backends. Text is normalised before comparison (lowercase, no "
        "punctuation, number words as digits). Recordings are not included.",
        "",
        "| Backend | Word error rate | Exactly right | Median time | Failed |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name in names:
        s = summaries[name]
        lines.append(
            f"| {name} | {s['wer']:.1%} | {s['exact']} of {len(samples)} | "
            f"{s['median_seconds']:.2f} s | {s['failed']} |"
        )
    lines += [
        "",
        "| # | Phrase | " + " | ".join(names) + " |",
        "| --- | --- | " + " | ".join("---" for _ in names) + " |",
    ]
    for index, (expected, _) in enumerate(samples):
        heard = []
        for name in names:
            row = results[name][index]
            mark = "✓" if row["wer"] == 0 else ("—" if row["wer"] is None else f"{row['wer']:.0%}")
            heard.append(f"{cell(row['heard'])} ({mark})")
        lines.append(f"| {index + 1} | {cell(expected)} | " + " | ".join(heard) + " |")
    OUTPUT.write_text("\n".join(lines) + "\n")

    for name in names:
        s = summaries[name]
        print(
            f"{name}: WER {s['wer']:.1%}, exactly right {s['exact']}/{len(samples)}, "
            f"median {s['median_seconds']:.2f}s, failed {s['failed']}"
        )
    print(f"Report written to {OUTPUT}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["record", "compare"])
    args = parser.parse_args()
    config = load_config()
    record(config) if args.command == "record" else compare(config)


if __name__ == "__main__":
    main()
