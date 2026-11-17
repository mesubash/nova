"""Measure whether spoken Nepali commands lead to the intended action.

    python scripts/command_benchmark.py record
    python scripts/command_benchmark.py compare   # billable Gemini calls

Each recording is transcribed by Gemini in Nepali mode and the transcript is sent to the model
in a fresh conversation; the typed phrase is also sent, to separate transcription failures from
understanding failures. Proposed actions are validated against a test policy and compared with
the expected action. Nothing is ever executed. Recordings stay in
~/Library/Application Support/NOVA/voice-samples/commands and are never committed.
"""

import argparse
import dataclasses
import json
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

from voice_benchmark import PhraseSet, record, samples_dir

from nova.actions import (
    Action,
    ActionPolicy,
    ActionRejected,
    ActionRequest,
    DeleteNote,
    EditNote,
    ListNotes,
    OpenApp,
    OpenUrl,
    SaveNote,
    SearchFiles,
    SearchNotes,
    validate,
)
from nova.ai import AIError, GeminiClient, Message
from nova.config import load_config
from nova.storage import NoteStore

# An expectation is (action type, {field: accepted substrings}); None means no action.
# A list of expectations means any one of them is correct.
Expected = tuple[type, dict[str, tuple[str, ...]]] | None
COMMANDS: list[tuple[str, list[Expected]]] = [
    ("सफारी खोल्नुहोस्।", [(OpenApp, {"app": ("Safari",)})]),
    ("Safari खोल्नुहोस्।", [(OpenApp, {"app": ("Safari",)})]),
    ("नोट्स खोल्नुहोस्।", [(OpenApp, {"app": ("Notes",)})]),
    ("क्यालेन्डर खोल्नुहोस्।", [(OpenApp, {"app": ("Calendar",)})]),
    ("क्याल्कुलेटर खोलिदिनुस्।", [(OpenApp, {"app": ("Calculator",)})]),
    ("GitHub मा जानुहोस्।", [(OpenUrl, {"url": ("github.com",)})]),
    ("YouTube खोल्नुहोस्।", [(OpenUrl, {"url": ("youtube.com",)})]),
    (
        "Safari खोल्नुहोस् र GitHub मा जानुहोस्।",
        [(OpenUrl, {"url": ("github.com",)}), (OpenApp, {"app": ("Safari",)})],
    ),
    ("मेरा नोटहरू देखाउनुहोस्।", [(ListNotes, {})]),
    ("एउटा नोट सेभ गर्नुहोस्: दूध र रोटी किन्नु।", [(SaveNote, {"text": ("दूध", "milk")})]),
    ("दूधको बारेमा नोट खोज्नुहोस्।", [(SearchNotes, {"query": ("दूध", "milk")})]),
    ("नोट तीन मेटाउनुहोस्।", [(DeleteNote, {"note_id": ("3",)})]),
    (
        "नोट दुई बदल्नुहोस्: आइतबार दाइलाई फोन गर्नु।",
        [(EditNote, {"note_id": ("2",), "text": ("आइतबार", "sunday")})],
    ),
    ("मेरो फाइलमा invoice खोज्नुहोस्।", [(SearchFiles, {"query": ("invoice", "इनभ्वाइस")})]),
    ("नेपालको राजधानी कहाँ हो?", [None]),
    ("नोट भनेको के हो?", [None]),
]
PHRASES = PhraseSet("ne", "commands", Path("docs/command-results.md"), [p for p, _ in COMMANDS])
EXPECTED = dict(COMMANDS)
PAUSE_SECONDS = 4.5  # stays under the free tier's 15 requests per minute


def matches(action: Action | None, expected: list[Expected]) -> bool:
    """True if the validated action (None = no action) equals any accepted expectation."""
    for option in expected:
        if option is None:
            if action is None:
                return True
            continue
        kind, fields = option
        if isinstance(action, kind) and all(
            any(_field_matches(getattr(action, name), want) for want in accepted)
            for name, accepted in fields.items()
        ):
            return True
    return False


def _field_matches(value: object, want: str) -> bool:
    """Text fields match a substring (ignoring case); numbers must be equal."""
    if isinstance(value, str):
        return want.casefold() in value.casefold()
    return str(value) == want


def propose(client: GeminiClient, text: str, policy: ActionPolicy) -> tuple[Action | None, str]:
    """Return (validated action or None, description) for one user message."""
    reply = client.reply([Message("user", text)])
    if not isinstance(reply, ActionRequest):
        return None, "text reply"
    try:
        action = validate(reply, policy)
    except ActionRejected as exc:
        return None, f"rejected {reply.name} {reply.args}: {exc}"
    return action, action.describe().replace(
        str(policy.search_folder.resolve()), "the approved folder"
    )


def compare() -> None:
    config = dataclasses.replace(load_config(), speech_language="ne")
    folder = samples_dir(config, PHRASES)
    manifest_path = folder / "manifest.json"
    if not manifest_path.exists():
        sys.exit("No recordings yet. Run: python scripts/command_benchmark.py record")
    samples = [
        (item["text"], (folder / item["file"]).read_bytes())
        for item in json.loads(manifest_path.read_text())
    ]

    client = GeminiClient(config)
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "approved").mkdir()
        notes = NoteStore(root / "notes.db")
        for text in ("Buy milk and bread", "Call my brother", "Pay the electricity bill"):
            notes.add(text)
        policy = ActionPolicy(config.allowed_apps, root / "approved", notes)
        calls = 0

        def pace() -> None:
            nonlocal calls
            if calls:
                time.sleep(PAUSE_SECONDS)
            calls += 1

        try:
            for index, (phrase, wav) in enumerate(samples, start=1):
                expected = EXPECTED[phrase]
                row = {"phrase": phrase}
                try:
                    pace()
                    row["heard"] = client.transcribe(wav)
                    if row["heard"]:
                        pace()
                        action, row["spoken"] = propose(client, row["heard"], policy)
                        row["spoken_ok"] = matches(action, expected)
                    else:  # the app asks the user to try again; nothing reaches the model
                        row["spoken"], row["spoken_ok"] = "no speech heard", False
                    pace()
                    action, row["typed"] = propose(client, phrase, policy)
                    row["typed_ok"] = matches(action, expected)
                except AIError as exc:
                    row.setdefault("heard", "—")
                    row["failed"] = str(exc)
                rows.append(row)
                print(f"{index:2}/{len(samples)} {mark(row, 'spoken')} {phrase}")
        finally:
            client.close()

    write_report(rows, config.model)


def mark(row: dict, key: str) -> str:
    if "failed" in row and f"{key}_ok" not in row:
        return "—"
    return "✓" if row[f"{key}_ok"] else "✗"


def cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def write_report(rows: list[dict], model: str) -> None:
    measured = [row for row in rows if "failed" not in row]
    spoken = sum(row["spoken_ok"] for row in measured)
    typed = sum(row["typed_ok"] for row in measured)
    lines = [
        "# Nepali voice command results",
        "",
        f"Run on {date.today().isoformat()} with `{model}` using `scripts/command_benchmark.py`: "
        f"{len(rows)} commands read aloud by the developer (MacBook Air M4, built-in "
        "microphone), transcribed by Gemini in Nepali mode, and sent to the model in a fresh "
        "conversation. The typed phrase was also sent, to separate transcription failures "
        "from understanding failures. Proposed actions were validated against a test policy "
        "and compared with the expected action. **Nothing was executed.** Recordings are not "
        "included.",
        "",
        f"**Spoken:** {spoken} of {len(measured)} correct · **Typed:** {typed} of "
        f"{len(measured)} correct · {len(rows) - len(measured)} request failed",
        "",
        "| # | Phrase | Heard | Spoken → action | Typed → action |",
        "| --- | --- | --- | --- | --- |",
    ]
    for index, row in enumerate(rows, start=1):
        if "failed" in row:
            lines.append(
                f"| {index} | {cell(row['phrase'])} | {cell(row['heard'])} | "
                f"failed: {cell(row['failed'])} | — |"
            )
            continue
        lines.append(
            f"| {index} | {cell(row['phrase'])} | {cell(row['heard'])} | "
            f"{cell(row['spoken'])} ({mark(row, 'spoken')}) | "
            f"{cell(row['typed'])} ({mark(row, 'typed')}) |"
        )
    PHRASES.output.write_text("\n".join(lines) + "\n")
    print(f"\nSpoken {spoken}/{len(measured)}, typed {typed}/{len(measured)}.")
    print(f"Report written to {PHRASES.output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["record", "compare"])
    args = parser.parse_args()
    if args.command == "record":
        record(load_config(), PHRASES)
    else:
        compare()


if __name__ == "__main__":
    main()
