"""Run blocking work off the UI thread, one task at a time."""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from PySide6.QtCore import QObject, Signal


class TaskRunner(QObject):
    """Runs one blocking function at a time on a background thread.

    Results arrive on the UI thread through the `succeeded` and `failed` signals.
    Cancelling makes the running task's result "late", and late results are dropped.
    """

    succeeded = Signal(object)
    failed = Signal(object)
    _done = Signal(int, object, object)  # task id, result, error

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nova-task")
        self._current_id = 0
        self._busy = False
        self._done.connect(self._on_done)

    @property
    def busy(self) -> bool:
        return self._busy

    def start(self, func: Callable[[], Any]) -> bool:
        """Run `func` in the background. Returns False if a task is already running."""
        if self._busy:
            return False
        self._current_id += 1
        self._busy = True
        self._executor.submit(self._run, self._current_id, func)
        return True

    def cancel(self) -> None:
        """Stop waiting for the running task. Its result will be ignored."""
        self._current_id += 1
        self._busy = False

    def shutdown(self) -> None:
        """Cancel and release the worker thread without waiting for it."""
        self.cancel()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _run(self, task_id: int, func: Callable[[], Any]) -> None:
        # Runs on the background thread.
        try:
            result = func()
        except Exception as exc:
            self._emit_done(task_id, None, exc)
        else:
            self._emit_done(task_id, result, None)

    def _emit_done(self, task_id: int, result: Any, error: Exception | None) -> None:
        try:
            self._done.emit(task_id, result, error)
        except RuntimeError:
            pass  # the window was closed and this object deleted; nobody is listening

    def _on_done(self, task_id: int, result: Any, error: Exception | None) -> None:
        # Runs on the UI thread, because this object lives there.
        if task_id != self._current_id:
            return
        self._busy = False
        if error is not None:
            self.failed.emit(error)
        else:
            self.succeeded.emit(result)
