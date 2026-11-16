"""
AI tools: press a key.

``press_key`` takes one of twelve keys. The tool sweep covers the Windows key and Windows+D;
this covers the other ten. The practice page opens with its key practice box focused, and the
box reports every key that reaches it, so each row checks that the key LIMA was asked for is
the key that arrived: Tab, not Shift+Tab; the Up arrow, not the Down arrow.
"""

import time

from ai_tool_tests import _common
from lima_practice_page import KEY_BOX_NAME

KEY_BOX_ID = "key-box"

# (the tool's key name, how a user says it, the key the page reports, whether Shift is held)
CASES = (
    ("enter", "the Enter key", "Enter", False),
    ("backspace", "the Backspace key", "Backspace", False),
    ("up", "the Up Arrow key", "ArrowUp", False),
    ("down", "the Down Arrow key", "ArrowDown", False),
    ("left", "the Left Arrow key", "ArrowLeft", False),
    ("right", "the Right Arrow key", "ArrowRight", False),
    ("tab", "the Tab key", "Tab", False),
    ("shift+tab", "Shift+Tab", "Tab", True),
    ("space", "the Space bar", " ", False),
    ("escape", "the Escape key", "Escape", False),
)


def case_name(case):
    result_name = f"AI tools: press {case[0]}"
    return result_name


def _arrived(page, since, reported_key, shift):
    """Wait for the key to reach the key box; True when it did, with Shift as expected."""
    deadline = time.time() + _common.EVENT_TIMEOUT
    while True:
        for event in page.events("key", target=KEY_BOX_NAME, since=since):
            detail = event["detail"]
            if detail.get("key") == reported_key and bool(detail.get("shift")) == shift:
                return True
        if time.time() >= deadline:
            return False
        time.sleep(0.2)


def _check_for(spoken, reported_key, shift):
    def check(page, since):
        if _arrived(page, since, reported_key, shift):
            outcome = f"The key practice box received {spoken}."
            return True, outcome
        outcome = f"The key practice box never received {spoken}."
        return False, outcome
    return check


def run_case(executor, case):
    _key, spoken, reported_key, shift = case
    instruction = f"Press {spoken} once."
    check = _check_for(spoken, reported_key, shift)
    _common.run_page_test(executor, case_name(case), instruction, check, focus=KEY_BOX_ID)
