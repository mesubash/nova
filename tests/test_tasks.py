import threading

import pytest

from nova.ui.tasks import TaskRunner


@pytest.fixture
def runner(qtbot):
    runner = TaskRunner()
    yield runner
    runner.shutdown()


def test_result_is_delivered_on_ui_thread(qtbot, runner):
    threads = {}

    def work():
        threads["work"] = threading.get_ident()
        return 42

    runner.succeeded.connect(lambda result: threads.setdefault("slot", threading.get_ident()))
    with qtbot.waitSignal(runner.succeeded, timeout=2000) as blocker:
        assert runner.start(work)

    assert blocker.args == [42]
    assert threads["work"] != threading.get_ident()
    assert threads["slot"] == threading.get_ident()
    assert not runner.busy


def test_error_is_delivered_through_failed_signal(qtbot, runner):
    def work():
        raise ValueError("boom")

    with qtbot.waitSignal(runner.failed, timeout=2000) as blocker:
        runner.start(work)
    assert isinstance(blocker.args[0], ValueError)


def test_only_one_task_runs_at_a_time(qtbot, runner):
    release = threading.Event()
    with qtbot.waitSignal(runner.succeeded, timeout=2000):
        assert runner.start(lambda: release.wait(2))
        assert runner.busy
        assert not runner.start(lambda: "second")
        release.set()


def test_cancelled_result_is_dropped(qtbot, runner):
    release = threading.Event()
    runner.start(lambda: release.wait(2) and "late")
    runner.cancel()
    assert not runner.busy
    with qtbot.assertNotEmitted(runner.succeeded, wait=300):
        release.set()


def test_new_task_after_cancel_gets_only_its_own_result(qtbot, runner):
    release = threading.Event()
    runner.start(lambda: release.wait(2) and "old")
    runner.cancel()
    with qtbot.waitSignal(runner.succeeded, timeout=3000) as blocker:
        runner.start(lambda: "new")
        release.set()
    assert blocker.args == ["new"]


def test_on_success_callback_receives_result(qtbot, runner):
    received = []
    runner.start(lambda: 7, on_success=received.append)
    qtbot.waitUntil(lambda: received == [7], timeout=2000)


def test_callback_can_start_the_next_task(qtbot, runner):
    received = []
    runner.start(
        lambda: 1,
        on_success=lambda first: runner.start(lambda: first + 1, on_success=received.append),
    )
    qtbot.waitUntil(lambda: received == [2], timeout=2000)
