"""Validated desktop actions. The model proposes; this package decides and executes."""

from nova.actions.execute import ActionResult, execute
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
    "Action",
    "ActionPolicy",
    "ActionRejected",
    "ActionRequest",
    "ActionResult",
    "OpenApp",
    "OpenUrl",
    "SearchFiles",
    "execute",
    "validate",
]
