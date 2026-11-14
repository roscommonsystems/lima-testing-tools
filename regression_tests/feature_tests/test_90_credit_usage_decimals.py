"""
Feature: Credit usage to two decimal places.

LIMA 2.1.0.5 shows the account's credit use at the top of File > Subscription Information
(subscription_dialog.py, ``_usage_text`` ~L217). The formatter has three branches:

  * still fetching      -> "Credits Used: checking…"            (no percentage)
  * no percentage known -> "Credits Used: Not available"         (no percentage)
  * a percentage        -> ``f"{percent:.2f}"`` (L239) plus "%"         (always exactly two decimals)

The two-decimal formatting is the fix this test guards: a whole number, or a server that still
sends an integer, must still read "12.00%", and a raw float must never leak "12.3456%" into a
line a screen-reader user hears. The Vietnamese UI writes a decimal comma instead of a dot, so
both separators are accepted — the count of decimals is what matters, not which separator.

The line is read straight off the dialog over UI Automation (the accessible names the plan and
version rows already use), never from a screenshot or LIMA's log. If the dialog itself shows no
percentage because the plan or the network cannot answer, that is the environment, not a
regression, so the test reports SKIPPED with the exact text it saw. A percentage with the wrong
number of decimals is always a failure.
"""

import re
import time

import pyautogui
import uiautomation as auto

from lima_test_utils import (
    TEST_PASSED, TEST_FAILED, TEST_SKIPPED, open_file_menu_item, SLEEP_A, SLEEP_B,
)
from feature_tests import _common

RESULT_NAME = "Feature: Credit usage to two decimal places"

# The File-menu route the tool sweep already uses for this dialog (lima_tool_tests.py
# "SUBSCRIPTION DIALOG": menu item by accessible name, Down then Enter as the key fallback).
MENU_ITEM_NAME = "Subscription Information"
MENU_NAV_KEYS = ["down", "enter"]
DIALOG_TITLE = "Subscription Information"

# Both label variants start with this ("Credits Used this month" for a monthly plan, plain
# "Credits Used" for a one-time budget or an unknown reset policy).
USAGE_LABEL_PREFIX = "credits used"

# Exactly two decimal places, a dot or a comma, then the percent sign.
TWO_DECIMALS_RE = re.compile(r"\d+[.,]\d{2}\s*%")

# The dialog opens at once; its tree can lag a moment behind the window.
DIALOG_TIMEOUT = 20.0

# The usage line is filled in by a worker that refreshes a token and calls the AI server. Slow
# networks are normal, so wait longer than a turn before calling it unavailable.
USAGE_TIMEOUT = 60.0

MAX_TREE_NODES = 4000


def _find_dialog(title_keyword, timeout=DIALOG_TIMEOUT):
    """
    The open dialog window whose name contains title_keyword, or None on timeout.

    Walks the UIA tree from the desktop rather than assuming the dialog is a direct child:
    Qt dialogs with a parent are usually top-level windows, but the depth is not guaranteed.
    Matching on ControlType keeps a same-named menu item (the File menu this test just clicked)
    from being mistaken for the dialog.
    """
    deadline = time.time() + timeout
    while True:
        root = auto.GetRootControl()
        stack = [(child, 0) for child in root.GetChildren()]
        seen = 0
        while stack and seen < MAX_TREE_NODES:
            control, depth = stack.pop()
            seen += 1
            try:
                if (control.ControlTypeName in ("WindowControl", "PaneControl")
                        and title_keyword.lower() in (control.Name or "").lower()):
                    return control
                if depth < 6:
                    stack.extend((child, depth + 1) for child in control.GetChildren())
            except Exception:
                continue
        if time.time() >= deadline:
            return None
        time.sleep(0.5)


def _control_texts(control):
    """Every non-empty accessible name in the dialog's subtree, in tree order, deduplicated."""
    names = []
    stack = [(control, 0)]
    seen = 0
    while stack and seen < MAX_TREE_NODES:
        current, depth = stack.pop()
        seen += 1
        try:
            name = (current.Name or "").strip()
            if name and name not in names:
                names.append(name)
            if depth < 20:
                stack.extend((child, depth + 1) for child in current.GetChildren())
        except Exception:
            continue
    return names


def _usage_line(names):
    """The first line that starts with "Credits Used", or None."""
    for name in names:
        if name.strip().lower().startswith(USAGE_LABEL_PREFIX):
            return name.strip()
    return None


def _wait_for_usage_line(control, timeout=None):
    """
    The usage line once it is no longer "checking…", or whatever it last said on timeout.

    The pending text is translated and ends in an ellipsis, so this checks for the word
    "checking" rather than the exact sentence; a line with a percentage is returned at once.
    """
    timeout = USAGE_TIMEOUT if timeout is None else timeout
    deadline = time.time() + timeout
    line = None
    while True:
        line = _usage_line(_control_texts(control)) or line
        if line and "checking" not in line.lower():
            return line
        if time.time() >= deadline:
            return line
        time.sleep(1.0)


def _dialog_still_open(control):
    """True while the dialog window still exists."""
    try:
        hwnd = control.NativeWindowHandle
        if hwnd:
            return _common.is_open(hwnd)
    except Exception:
        pass
    try:
        return bool(control.Exists(maxSearchSeconds=0.2))
    except Exception:
        return False


def _find_button(control, names):
    """A button in the dialog whose accessible name or text is one of names (case-insensitive)."""
    wanted = {name.lower() for name in names}
    stack = [(control, 0)]
    seen = 0
    while stack and seen < MAX_TREE_NODES:
        current, depth = stack.pop()
        seen += 1
        try:
            if (current.ControlTypeName == "ButtonControl"
                    and (current.Name or "").strip().lower() in wanted):
                return current
            if depth < 20:
                stack.extend((child, depth + 1) for child in current.GetChildren())
        except Exception:
            continue
    return None


def _close_dialog(control):
    """
    Close the dialog with its Close button, falling back to Escape.

    Returns:
        bool: True when the dialog is gone.
    """
    if not _dialog_still_open(control):
        return True
    button = _find_button(control, ("Close Subscription Dialog Button", "Close"))
    if button is not None:
        try:
            print("  Closing the dialog with its Close button")
            button.Click()
        except Exception as error:
            print(f"  ! Close button click failed: {error}")
    if not _common.wait_until(lambda: not _dialog_still_open(control), 5.0):
        print("  ! Close button did not close the dialog; pressing Escape")
        try:
            control.SetFocus()
        except Exception:
            pass
        pyautogui.press("escape")
        time.sleep(SLEEP_A)
    return not _dialog_still_open(control)


def _open_dialog(executor):
    """
    Open File > Subscription Information and return its UIA control (or None).

    Two attempts: a keypress can be swallowed while LIMA is settling, and the legacy nav keys
    in open_file_menu_item need the menu focused.
    """
    for attempt in range(1, 3):
        if not _common.ensure_lima_ready(executor):
            continue
        print(f"  Opening File > {MENU_ITEM_NAME} (attempt {attempt})")
        open_file_menu_item(MENU_ITEM_NAME, MENU_NAV_KEYS)
        time.sleep(SLEEP_B)
        dialog = _find_dialog(DIALOG_TITLE)
        if dialog is not None:
            return dialog
    return None


def _run_case(executor, opened):
    """Do the scenario; return (status, message). opened receives the dialog for cleanup."""
    dialog = _open_dialog(executor)
    if dialog is None:
        return TEST_FAILED, (f"File > {MENU_ITEM_NAME} did not open a {DIALOG_TITLE!r} dialog "
                             f"within {DIALOG_TIMEOUT:.0f}s of clicking the menu item")
    opened.append(dialog)

    line = _wait_for_usage_line(dialog)
    if not line:
        seen = _control_texts(dialog)[:25]
        return TEST_FAILED, (f"No line starting with 'Credits Used' was found in the "
                             f"{DIALOG_TITLE} dialog after {USAGE_TIMEOUT:.0f}s. Texts seen: "
                             f"{seen!r}")

    print(f"  Usage line: {line!r}")

    if TWO_DECIMALS_RE.search(line):
        return TEST_PASSED, (f"The dialog shows the credit use to two decimal places: {line!r}")

    if "%" in line:
        return TEST_FAILED, (f"The credit usage line does not show two decimal places: {line!r}. "
                             "subscription_dialog._usage_text formats the percentage with "
                             "'{percent:.2f}' (two decimals), so it must read like '12.34%' "
                             "(or '12,34%' in Vietnamese).")

    # No percentage at all: the plan or the network could not answer. That is the environment,
    # not the formatter, so it is reported as skipped with the exact text.
    return TEST_SKIPPED, (f"The dialog shows no credit percentage, so there was nothing to "
                          f"format: {line!r}. The formatter's other branches are 'checking…' "
                          f"while the server is asked and 'Not available' when the plan or the "
                          f"network cannot report a percentage.")


def run(executor):
    """Run the test and report exactly one result."""
    status, message = TEST_FAILED, "The test did not run"
    opened = []
    try:
        status, message = _run_case(executor, opened)
    except Exception as error:
        status, message = TEST_FAILED, f"Exception during the test: {error}"
    finally:
        # Close the dialog whatever happened: it is modal, so leaving it open would block the
        # next test's keystrokes into LIMA.
        for dialog in opened:
            if not _close_dialog(dialog):
                message += (" CLEANUP FAILED: the subscription dialog is still open; the next "
                            "test's keystrokes may go to it.")
                print("  ! The subscription dialog is still open")
        time.sleep(SLEEP_A)

    executor.add_test_result(RESULT_NAME, status, message)
    if status == TEST_PASSED:
        print("  OK " + message)
    elif status == TEST_SKIPPED:
        print("  - SKIPPED " + message)
    else:
        print("  X " + message)
