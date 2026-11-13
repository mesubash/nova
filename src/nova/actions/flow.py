"""The decide-then-act sequence: validate, confirm if needed, then execute."""

from collections.abc import Callable

from nova.actions.execute import ActionResult, execute
from nova.actions.validate import Action, ActionPolicy, ActionRejected, ActionRequest, validate

CANCELLED = ActionResult(False, "Cancelled. Nothing was done.")


def rejection(exc: ActionRejected) -> ActionResult:
    return ActionResult(False, f"I can't do that. {exc}")


def run_action(
    request: ActionRequest,
    policy: ActionPolicy,
    confirm: Callable[[Action], bool],
    execute_action: Callable[[Action], ActionResult] = execute,
) -> ActionResult:
    """Validate, ask for confirmation if the action has side effects, then execute.

    Never raises for a bad proposal: every path returns a result to show the user.
    """
    try:
        action = validate(request, policy)
    except ActionRejected as exc:
        return rejection(exc)
    if action.requires_confirmation and not confirm(action):
        return CANCELLED
    return execute_action(action)
