"""Measure transcription accuracy on your own voice: Gemini versus local Whisper.

    python scripts/voice_benchmark.py record  [--set english|nepali]
    python scripts/voice_benchmark.py compare [--set english|nepali]   # billable Gemini calls

Recordings stay in ~/Library/Application Support/NOVA/voice-samples and are never committed.
`compare` writes a results file under docs/ containing text only, no audio.
"""

import argparse
import json
import statistics
import sys
import time
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from nova.__main__ import wait_for_enter
from nova.ai import AIError, GeminiClient
from nova.config import Config, load_config
from nova.speech import Recorder, RecordingError
from nova.transcription import LocalTranscriber, TranscriptionError


@dataclass(frozen=True)
class PhraseSet:
    language: str  # Whisper language code
    folder: str  # subfolder of voice-samples ("" = the folder itself)
    output: Path
    phrases: list[str]


SETS = {
    "english": PhraseSet(
        "en",
        "",
        Path("docs/transcription-results.md"),
        [
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
        ],
    ),
    "nepali": PhraseSet(
        "ne",
        "nepali",
        Path("docs/transcription-results-nepali.md"),
        [
            "नेपालको राजधानी कहाँ हो?",
            "आज मौसम कस्तो छ?",
            "पोखरा काठमाडौंबाट कति टाढा छ?",
            "राम्रो निद्राको लागि एउटा सुझाव दिनुहोस्।",
            "सफारी खोल्नुहोस्।",
            "मेरा नोटहरू देखाउनुहोस्।",
            "एउटा नोट सेभ गर्नुहोस्: दूध र रोटी किन्नु।",
            "नोट तीन मेटाउनुहोस्।",
            "न्युरल नेटवर्क भनेको के हो, सजिलो भाषामा बताउनुहोस्।",
            "धन्यवाद, अहिलेलाई यति नै।",
            "मेरो meeting कति बजे छ?",
            "Safari खोल्नुहोस् र GitHub मा जानुहोस्।",
        ],
    ),
}
MAX_SECONDS = 15
PAUSE_SECONDS = 4.5  # stays under the free tier's 15 requests per minute
DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
NUMBER_WORDS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "एक": "1",
    "दुई": "2",
    "तीन": "3",
    "चार": "4",
    "पाँच": "5",
    "सात": "7",
    "आठ": "8",
    "नौ": "9",
    "दस": "10",
}  # fmt: skip  ("छ", six, is excluded: it is also the everyday verb "is")


def samples_dir(config: Config, phrase_set: PhraseSet) -> Path:
    return config.data_dir / "voice-samples" / phrase_set.folder


def words(text: str) -> list[str]:
    """Lowercase, remove punctuation and symbols (keeping Devanagari vowel signs), unify numbers."""
    text = unicodedata.normalize("NFC", text.lower()).translate(DEVANAGARI_DIGITS)
    cleaned = "".join(" " if unicodedata.category(char)[0] in "PS" else char for char in text)
    return [NUMBER_WORDS.get(word, word) for word in cleaned.split()]


def edit_distance(reference: Sequence, hypothesis: Sequence) -> int:
    """Minimum substitutions + insertions + deletions turning hypothesis into reference."""
    previous = list(range(len(hypothesis) + 1))
    for i, ref_item in enumerate(reference, start=1):
        current = [i]
        for j, hyp_item in enumerate(hypothesis, start=1):
            current.append(
                min(
                    previous[j] + 1,  # deletion
                    current[j - 1] + 1,  # insertion
                    previous[j - 1] + (ref_item != hyp_item),  # substitution
                )
            )
        previous = current
    return previous[-1]


def word_error_rate(expected: str, heard: str) -> float:
    reference = words(expected)
    return edit_distance(reference, words(heard)) / max(len(reference), 1)


def character_error_rate(expected: str, heard: str) -> float:
    reference = " ".join(words(expected))
    return edit_distance(reference, " ".join(words(heard))) / max(len(reference), 1)


def record(config: Config, phrase_set: PhraseSet) -> None:
    folder = samples_dir(config, phrase_set)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    recorder = Recorder(MAX_SECONDS)
    manifest = []
    print("Read each phrase naturally, in your normal voice and speed.\n")
    for index, phrase in enumerate(phrase_set.phrases, start=1):
        while True:
            input(
                f'[{index}/{len(phrase_set.phrases)}] "{phrase}"\n'
                "  Press Enter, read it, then press Enter. "
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
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"\nSaved {len(manifest)} recordings to {folder}")


def compare(config: Config, set_name: str, phrase_set: PhraseSet) -> None:
    folder = samples_dir(config, phrase_set)
    manifest_path = folder / "manifest.json"
    if not manifest_path.exists():
        sys.exit(
            f"No recordings yet. Run: python scripts/voice_benchmark.py record --set {set_name}"
        )
    samples = [
        (item["text"], (folder / item["file"]).read_bytes())
        for item in json.loads(manifest_path.read_text())
    ]

    client = GeminiClient(config)
    local = LocalTranscriber(config.local_model, language=phrase_set.language)
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
                results[name].append(
                    {
                        "heard": heard,
                        "seconds": time.perf_counter() - start,
                        "wer": None if failed else word_error_rate(expected, heard),
                        "cer": None if failed else character_error_rate(expected, heard),
                    }
                )
            print(f"{index:2}/{len(samples)} {expected}")
    finally:
        client.close()

    print()
    write_report(samples, results, set_name, phrase_set)


def summarise(rows: list[dict]) -> dict:
    measured = [row for row in rows if row["wer"] is not None]
    if not measured:
        return {
            "wer": float("nan"),
            "cer": float("nan"),
            "exact": 0,
            "seconds": 0,
            "failed": len(rows),
        }
    return {
        "wer": statistics.mean(row["wer"] for row in measured),
        "cer": statistics.mean(row["cer"] for row in measured),
        "exact": sum(row["wer"] == 0 for row in measured),
        "seconds": statistics.median(row["seconds"] for row in measured),
        "failed": len(rows) - len(measured),
    }


def cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def write_report(samples, results, set_name: str, phrase_set: PhraseSet) -> None:
    names = list(results)
    summaries = {name: summarise(rows) for name, rows in results.items()}
    lines = [
        f"# Transcription accuracy on a real voice ({set_name})",
        "",
        f"Run on {date.today().isoformat()} with `scripts/voice_benchmark.py --set {set_name}`: "
        f"{len(samples)} phrases read aloud by the developer (MacBook Air M4, built-in "
        f"microphone), each transcribed by both backends; local Whisper was told the language "
        f"is `{phrase_set.language}`. Text is normalised before comparison (lowercase, no "
        "punctuation, numbers unified). Gemini times include any rate-limit waits. Recordings "
        "are not included.",
        "",
        "| Backend | Word error rate | Character error rate | Exactly right | "
        "Median time | Failed |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name in names:
        s = summaries[name]
        lines.append(
            f"| {name} | {s['wer']:.1%} | {s['cer']:.1%} | {s['exact']} of {len(samples)} | "
            f"{s['seconds']:.2f} s | {s['failed']} |"
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
    phrase_set.output.write_text("\n".join(lines) + "\n")

    for name in names:
        s = summaries[name]
        print(
            f"{name}: WER {s['wer']:.1%}, CER {s['cer']:.1%}, exactly right "
            f"{s['exact']}/{len(samples)}, median {s['seconds']:.2f}s, failed {s['failed']}"
        )
    print(f"Report written to {phrase_set.output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["record", "compare"])
    parser.add_argument("--set", dest="set_name", choices=sorted(SETS), default="english")
    args = parser.parse_args()
    config = load_config()
    phrase_set = SETS[args.set_name]
    if args.command == "record":
        record(config, phrase_set)
    else:
        compare(config, args.set_name, phrase_set)


if __name__ == "__main__":
    main()
