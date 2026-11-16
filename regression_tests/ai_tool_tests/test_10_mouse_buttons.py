"""
AI tools: click, right-click, double-click and move the mouse.

LIMA is asked to act on one named button of the practice page. It has to find the button on
screen from its name (``mouse_click`` / ``move_mouse_to`` with a ``target_element``) and put
the pointer on it. The page reports which button received which event, so a click that lands
on the wrong button, or a single click where a double-click was asked for, fails.

The three buttons sit side by side, and each row targets a different one, so "it clicked
something" is never enough to pass.
"""

from ai_tool_tests import _common

BUTTON_EVENTS = ("click", "double_click", "right_click")

# (result name, what LIMA is asked, the event that proves it, the button it must land on)
CASES = (
    ("AI tools: click a named button", "Click the Banana button.", "click", "Banana"),
    ("AI tools: right-click a named button", "Right-click the Cherry button.", "right_click", "Cherry"),
    ("AI tools: double-click a named button", "Double-click the Apple button.", "double_click", "Apple"),
    ("AI tools: move the mouse without clicking",
     "Move the mouse to the Banana button, but don't click it.", "hover", "Banana"),
)


def case_name(case):
    result_name = case[0]
    return result_name


def _check_for(event_kind, button):
    """The check for one row: the page saw event_kind on button after the instruction."""
    def check(page, since):
        event = page.wait_for_event(event_kind, target=button, timeout=_common.EVENT_TIMEOUT,
                                    since=since)
        if event is None:
            outcome = f"The page never recorded a {event_kind} on the {button} button."
            return False, outcome
        if event_kind == "hover":
            # Moving the mouse must not press anything: any button event since is a failure.
            presses = [pressed for kind in BUTTON_EVENTS for pressed in page.events(kind, since=since)]
            if presses:
                pressed_on = sorted({pressed["target"] for pressed in presses})
                outcome = (f"The pointer reached the {button} button, but something was also "
                           f"pressed: {pressed_on}.")
                return False, outcome
        outcome = f"The page recorded a {event_kind} on the {button} button."
        return True, outcome
    return check


def run_case(executor, case):
    result_name, instruction, event_kind, button = case
    check = _check_for(event_kind, button)
    _common.run_page_test(executor, result_name, instruction, check)
