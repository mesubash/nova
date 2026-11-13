import subprocess

import pytest

from nova.actions import (
    ActionPolicy,
    ActionRejected,
    ActionRequest,
    ActionResult,
    DeleteNote,
    EditNote,
    ListNotes,
    OpenApp,
    OpenUrl,
    SaveNote,
    SearchFiles,
    SearchNotes,
    execute,
    validate,
)
from nova.actions.execute import search_files
from nova.actions.flow import CANCELLED, run_action
from nova.storage import NoteStore


@pytest.fixture
def folder(tmp_path):
    root = tmp_path / "docs"
    (root / "reports").mkdir(parents=True)
    (root / "reports" / "Report-2026.pdf").write_text("x")
    (root / "budget.xlsx").write_text("x")
    (root / ".hidden-report.txt").write_text("x")
    (root / ".git").mkdir()
    (root / ".git" / "report-config").write_text("x")
    return root


@pytest.fixture
def policy(folder):
    return ActionPolicy(allowed_apps=("Safari", "Notes"), search_folder=folder)


def check(name, args, policy):
    return validate(ActionRequest(name, args), policy)


# Validation: apps


def test_allowed_app_uses_configured_spelling(policy):
    action = check("open_app", {"app": "safari"}, policy)
    assert action == OpenApp("Safari")
    assert action.requires_confirmation


def test_app_outside_allowlist_is_rejected(policy):
    with pytest.raises(ActionRejected, match="list of apps"):
        check("open_app", {"app": "Terminal"}, policy)


def test_unknown_action_is_rejected(policy):
    with pytest.raises(ActionRejected, match="Unknown action"):
        check("run_shell", {"command": "rm -rf ~"}, policy)


@pytest.mark.parametrize(
    "args",
    [
        {},
        {"app": 5},
        {"app": ""},
        {"app": "   "},
        {"name": "Safari"},
        {"app": "Safari", "extra": "x"},
        {"app": "Saf\x00ari"},
        {"app": "x" * 101},
        "Safari",
        None,
    ],
)
def test_malformed_arguments_are_rejected(policy, args):
    with pytest.raises(ActionRejected):
        check("open_app", args, policy)


# Validation: URLs


@pytest.mark.parametrize("url", ["https://example.com/path?q=1", "http://localhost:8000"])
def test_web_urls_are_accepted(policy, url):
    action = check("open_url", {"url": url}, policy)
    assert action == OpenUrl(url)
    assert action.requires_confirmation


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "ftp://example.com",
        "https://",
        "example.com",
        "https://exa mple.com",
        "-a Terminal",
        "http://[::1",
    ],
)
def test_unsafe_or_malformed_urls_are_rejected(policy, url):
    with pytest.raises(ActionRejected):
        check("open_url", {"url": url}, policy)


# Validation: search


def test_search_is_read_only_and_uses_configured_folder(policy, folder):
    action = check("search_files", {"query": "report"}, policy)
    assert action == SearchFiles("report", folder.resolve())
    assert not action.requires_confirmation


@pytest.mark.parametrize("query", ["../secret", "/etc/passwd", "reports/x", "..\\x"])
def test_search_query_cannot_contain_paths(policy, query):
    with pytest.raises(ActionRejected, match="file name only"):
        check("search_files", {"query": query}, policy)


def test_search_is_off_without_a_folder():
    policy = ActionPolicy(allowed_apps=(), search_folder=None)
    with pytest.raises(ActionRejected, match="NOVA_SEARCH_FOLDER"):
        check("search_files", {"query": "x"}, policy)


def test_search_rejects_a_folder_that_disappeared(tmp_path):
    policy = ActionPolicy(allowed_apps=(), search_folder=tmp_path / "gone")
    with pytest.raises(ActionRejected, match="does not exist"):
        check("search_files", {"query": "x"}, policy)


# Execution: open


class FakeRun:
    def __init__(self, returncode=0, stderr="", error=None):
        self.returncode = returncode
        self.stderr = stderr
        self.error = error
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error:
            raise self.error
        return subprocess.CompletedProcess(args, self.returncode, "", self.stderr)


def test_open_app_uses_argument_list_without_shell():
    run = FakeRun()
    result = execute(OpenApp("Safari"), run=run)
    args, kwargs = run.calls[0]
    assert args == ["open", "-a", "Safari"]
    assert "shell" not in kwargs
    assert result.ok
    assert result.message == "Opened Safari."


def test_open_url_passes_url_as_single_argument():
    run = FakeRun()
    execute(OpenUrl("https://example.com"), run=run)
    assert run.calls[0][0] == ["open", "https://example.com"]


def test_failed_open_reports_the_real_reason():
    run = FakeRun(returncode=1, stderr="Unable to find application named 'Notes'")
    result = execute(OpenApp("Notes"), run=run)
    assert not result.ok
    assert "Unable to find application" in result.message


def test_open_command_crash_is_reported():
    result = execute(OpenApp("Safari"), run=FakeRun(error=OSError("no open")))
    assert not result.ok


# Execution: search


def test_search_finds_nested_files_case_insensitively(folder):
    result = execute(SearchFiles("REPORT", folder))
    assert result.ok
    assert result.details == ("reports/Report-2026.pdf",)
    assert "Found 1 file" in result.message


def test_search_skips_hidden_files_and_folders(folder):
    result = execute(SearchFiles("report", folder))
    assert all(not part.startswith(".") for item in result.details for part in item.split("/"))


def test_search_never_leaves_the_folder_through_symlinks(folder, tmp_path):
    outside = tmp_path / "secret"
    outside.mkdir()
    (outside / "report-secret.txt").write_text("x")
    (folder / "report-link.txt").symlink_to(outside / "report-secret.txt")
    (folder / "linked-dir").symlink_to(outside, target_is_directory=True)

    result = execute(SearchFiles("report", folder))
    assert result.details == ("reports/Report-2026.pdf",)


def test_search_caps_number_of_results(tmp_path):
    for index in range(30):
        (tmp_path / f"note-{index:02}.txt").write_text("x")
    result = search_files(SearchFiles("note", tmp_path), max_results=5)
    assert len(result.details) == 5
    assert "5+" in result.message


def test_search_with_no_matches_says_so(folder):
    result = execute(SearchFiles("zzz", folder))
    assert result.ok
    assert result.details == ()
    assert "No files" in result.message


# The decide-then-act flow


def test_flow_rejects_without_asking(policy):
    asked = []
    result = run_action(ActionRequest("open_app", {"app": "Terminal"}), policy, asked.append)
    assert not result.ok
    assert "can't do that" in result.message
    assert asked == []


def test_declined_confirmation_executes_nothing(policy):
    executed = []
    result = run_action(
        ActionRequest("open_app", {"app": "Safari"}),
        policy,
        confirm=lambda action: False,
        execute_action=executed.append,
    )
    assert result == CANCELLED
    assert executed == []


def test_confirmed_action_is_executed(policy):
    result = run_action(
        ActionRequest("open_app", {"app": "safari"}),
        policy,
        confirm=lambda action: True,
        execute_action=lambda action: ActionResult(True, f"did {action.app}"),
    )
    assert result.message == "did Safari"


def test_read_only_search_runs_without_confirmation(policy):
    asked = []

    def confirm(action):
        asked.append(action)
        return False

    result = run_action(ActionRequest("search_files", {"query": "budget"}), policy, confirm)
    assert asked == []
    assert result.details == ("budget.xlsx",)


# Notes


@pytest.fixture
def notes(tmp_path):
    return NoteStore(tmp_path / "notes.db")


@pytest.fixture
def notes_policy(notes):
    return ActionPolicy(allowed_apps=(), search_folder=None, notes=notes)


def test_save_note_needs_confirmation_and_previews_text(notes_policy):
    action = check("save_note", {"text": "Buy milk"}, notes_policy)
    assert isinstance(action, SaveNote)
    assert action.requires_confirmation
    assert "Buy milk" in action.describe()


def test_listing_and_searching_notes_are_read_only(notes_policy):
    assert isinstance(check("list_notes", {}, notes_policy), ListNotes)
    assert not check("list_notes", {}, notes_policy).requires_confirmation
    assert isinstance(check("search_notes", {"query": "milk"}, notes_policy), SearchNotes)
    assert not check("search_notes", {"query": "milk"}, notes_policy).requires_confirmation


def test_list_notes_takes_no_arguments(notes_policy):
    with pytest.raises(ActionRejected, match="no arguments"):
        check("list_notes", {"limit": 5}, notes_policy)


@pytest.mark.parametrize("raw_id", [1, 1.0, "1", "#1", " 1 "])
def test_note_ids_accept_whole_numbers_in_common_forms(notes_policy, notes, raw_id):
    notes.add("Call mum")
    action = check("delete_note", {"id": raw_id}, notes_policy)
    assert action == DeleteNote(1, "Call mum", notes)
    assert "Call mum" in action.describe()


@pytest.mark.parametrize("raw_id", [True, 0, -1, 1.5, "abc", "²", None, [1]])
def test_invalid_note_ids_are_rejected(notes_policy, notes, raw_id):
    notes.add("x")
    with pytest.raises(ActionRejected):
        check("delete_note", {"id": raw_id}, notes_policy)


def test_missing_note_is_rejected_before_any_confirmation(notes_policy):
    with pytest.raises(ActionRejected, match="#9"):
        check("edit_note", {"id": 9, "text": "new"}, notes_policy)


def test_edit_preview_shows_old_and_new_text(notes_policy, notes):
    notes.add("Call mum")
    action = check("edit_note", {"id": 1, "text": "Call mum on Sunday"}, notes_policy)
    assert isinstance(action, EditNote)
    assert action.requires_confirmation
    assert '"Call mum"' in action.describe()
    assert "Sunday" in action.describe()


def test_note_actions_are_rejected_when_notes_are_unavailable(policy):
    with pytest.raises(ActionRejected, match="unavailable"):
        check("list_notes", {}, policy)


def test_note_actions_execute_against_the_store(notes_policy, notes):
    assert execute(check("save_note", {"text": "Buy milk"}, notes_policy)).message == (
        "Saved note #1."
    )
    execute(check("save_note", {"text": "Call dentist"}, notes_policy))

    listed = execute(check("list_notes", {}, notes_policy))
    assert len(listed.details) == 2
    assert "Call dentist" in listed.details[0]

    found = execute(check("search_notes", {"query": "milk"}, notes_policy))
    assert len(found.details) == 1
    assert "Buy milk" in found.details[0]

    assert execute(check("edit_note", {"id": 1, "text": "Buy oat milk"}, notes_policy)).ok
    assert notes.get(1).text == "Buy oat milk"

    assert execute(check("delete_note", {"id": 2}, notes_policy)).message == "Deleted note #2."
    assert [note.id for note in notes.recent()] == [1]


def test_empty_notes_list_says_so(notes_policy):
    assert execute(check("list_notes", {}, notes_policy)).message == "You have no notes yet."


def test_storage_failure_is_reported_not_raised(notes_policy, tmp_path):
    action = check("save_note", {"text": "x"}, notes_policy)
    (tmp_path / "notes.db").chmod(0o444)
    try:
        result = execute(action)
    finally:
        (tmp_path / "notes.db").chmod(0o600)
    assert not result.ok
    assert "notes database" in result.message


def test_declined_delete_keeps_the_note(notes_policy, notes):
    notes.add("keep me")
    result = run_action(
        ActionRequest("delete_note", {"id": 1}), notes_policy, confirm=lambda action: False
    )
    assert result == CANCELLED
    assert notes.get(1).text == "keep me"


# Adversarial proposals: whatever the model outputs, these must be rejected.

ATTACKS = [
    ("run_shell", {"command": "rm -rf ~"}),
    ("open_app", {"app": "Terminal"}),
    ("open_app", {"app": "S\u0430fari"}),  # Cyrillic "а" that looks like a Latin "a"
    ("open_app", {"app": "Saf\u200bari"}),  # zero-width space
    ("open_app", {"app": "Safari; open -a Terminal"}),
    ("open_app", {"app": "-a Terminal"}),
    ("open_app", {"app": "/System/Applications/Utilities/Terminal.app"}),
    ("open_app", {"app": "Safari", "then": "Terminal"}),
    ("open_url", {"url": "file:///etc/passwd"}),
    ("open_url", {"url": "JavaScript:alert(1)"}),
    ("open_url", {"url": "data:text/html,<script>alert(1)</script>"}),
    ("open_url", {"url": "https://user:secret@example.com"}),
    ("open_url", {"url": "https://example.com\\@evil.com"}),
    ("open_url", {"url": "https://exa\u202emple.com"}),  # right-to-left override
    ("search_files", {"query": "../../.ssh/id_rsa"}),
    ("search_files", {"query": "/etc/passwd"}),
    ("search_files", {"query": "report\u200b"}),
    ("delete_note", {"id": 10**30}),
    ("delete_note", {"id": "99999999999999999999"}),
    ("delete_note", {"id": -1}),
    ("edit_note", {"id": 0, "text": "hacked"}),
]


@pytest.fixture
def full_policy(folder, tmp_path):
    notes = NoteStore(tmp_path / "attack-notes.db")
    notes.add("existing note")
    return ActionPolicy(allowed_apps=("Safari", "Notes"), search_folder=folder, notes=notes)


@pytest.mark.parametrize(("name", "args"), ATTACKS)
def test_attack_proposals_are_rejected(full_policy, name, args):
    with pytest.raises(ActionRejected):
        check(name, args, full_policy)


def test_huge_note_number_is_rejected_not_crashing(full_policy):
    with pytest.raises(ActionRejected, match="too large"):
        check("delete_note", {"id": 10**30}, full_policy)
