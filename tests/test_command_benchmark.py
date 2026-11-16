import sys
from pathlib import Path

from nova.actions import DeleteNote, ListNotes, OpenApp, OpenUrl

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from command_benchmark import COMMANDS, matches  # noqa: E402


def test_matches_type_and_any_accepted_substring():
    assert matches(OpenApp("Safari"), [(OpenApp, {"app": ("Safari",)})])
    assert matches(OpenUrl("https://www.GitHub.com/"), [(OpenUrl, {"url": ("github.com",)})])
    assert not matches(OpenApp("Notes"), [(OpenApp, {"app": ("Safari",)})])
    assert not matches(ListNotes(None), [(OpenApp, {"app": ("Safari",)})])


def test_matches_any_option_and_no_action():
    either = [(OpenUrl, {"url": ("github.com",)}), (OpenApp, {"app": ("Safari",)})]
    assert matches(OpenApp("Safari"), either)
    assert matches(None, [None])
    assert not matches(OpenApp("Safari"), [None])
    assert not matches(None, either)


def test_note_id_compared_as_text():
    assert matches(DeleteNote(3, "x", None), [(DeleteNote, {"note_id": ("3",)})])
    assert not matches(DeleteNote(13, "x", None), [(DeleteNote, {"note_id": ("3",)})])


def test_phrases_are_unique():
    phrases = [phrase for phrase, _ in COMMANDS]
    assert len(phrases) == len(set(phrases))
