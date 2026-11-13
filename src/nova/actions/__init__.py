"""Validated desktop actions. The model proposes; this package decides and executes."""

from nova.actions.execute import ActionResult, execute
from nova.actions.flow import CANCELLED, rejection, run_action
from nova.actions.validate import (
    Action,
    ActionPolicy,
    ActionRejected,
    ActionRequest,
    OpenApp,
    OpenUrl,
    SearchFiles,
    validate,
)

__all__ = [
    "CANCELLED",
    "Action",
    "ActionPolicy",
    "ActionRejected",
    "ActionRequest",
    "ActionResult",
    "OpenApp",
    "OpenUrl",
    "SearchFiles",
    "execute",
    "rejection",
    "run_action",
    "validate",
]
