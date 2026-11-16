"""
Shared steps for the AI tool tests.

``run_page_test`` is the whole shape of one test: start LIMA, open the practice page in front,
send LIMA an instruction from there, wait for the turn to end, and let the test's own check
read what the page recorded. A test module is then just its instructions and checks.
"""

import time

import pyautogui

import lima_ui
from lima_action_approver import get_hotkey
from lima_practice_page import PracticePage, PracticePageError
from lima_test_utils import TEST_PASSED, TEST_FAILED, SLEEP_A, SLEEP_B
from approval_tests._common import cleanup, ensure_lima_ready
from feature_tests._common import describe_turn, wait_for_turn_end

# Title of the popup the quick input hotkey opens (quick_input_dialog.py).
QUICK_INPUT_TITLE = "Ask Lima"
QUICK_INPUT_TIMEOUT = 10.0

# How long after the turn ends an event may still arrive from the page. The page posts each
# event as it happens, so this only covers the browser being slow to send the last one.
EVENT_TIMEOUT = 5.0


def park_mouse(page):
    """
    Move the pointer to an empty part of the practice page; True when it could be placed.

    The page reports a hover as soon as the pointer is over a button, and LIMA clicks and
    scrolls at the pointer when it is given no target, so the pointer must start on nothing a
    test checks, but still over the page.
    """
    point = page.empty_point()
    if point is None:
        return False
    pyautogui.moveTo(*point)
    time.sleep(SLEEP_A)
    return True


def ask_lima_from_here(executor, text):
    """
    Send LIMA an instruction without leaving the program in front: quick input, type, Enter.

    This is how a keyboard user asks LIMA to act on the program they are in. The quick input
    hotkey opens the Ask Lima popup; when it closes, LIMA gives the focus back to the window
    that had it, so that window is what LIMA sees when it starts the turn.

    Returns:
        bool: True when the popup opened and closed again after Enter.
    """
    keys = get_hotkey("quick_input_hotkey", executor.process_manager.install_path)
    print(f"  Sending instruction to LIMA through quick input ({'+'.join(keys)}): {text!r}")
    pyautogui.hotkey(*keys)
    popup = lima_ui.wait_for_window(QUICK_INPUT_TITLE, timeout=QUICK_INPUT_TIMEOUT)
    if not popup:
        print(f"  ! The {QUICK_INPUT_TITLE!r} popup did not open")
        return False
    # The popup refocuses its field once the hotkey's Ctrl and Alt are released.
    time.sleep(SLEEP_B)
    popup_control = lima_ui.window_control(popup)
    field = lima_ui.find_control(popup_control, control_type="EditControl") if popup_control else None
    if field is not None:
        try:
            field.SetFocus()
            time.sleep(0.2)
        except Exception as error:
            print(f"  ! Could not focus the popup's input ({error}); typing anyway")
    pyautogui.write(text, interval=0.02)
    time.sleep(0.2)
    pyautogui.press("enter")
    closed = lima_ui.wait_until_closed(popup, timeout=QUICK_INPUT_TIMEOUT)
    if not closed:
        print(f"  ! The {QUICK_INPUT_TITLE!r} popup is still open after Enter")
    return closed


def _run_scenario(executor, page, instruction, check, focus):
    """Do one page test; return (passed, message)."""
    if not ensure_lima_ready(executor):
        return False, "LIMA was not running with its window ready, so the test could not run"

    query = {"focus": focus} if focus else {}
    page.start()
    page.open_in_browser(**query)
    if not park_mouse(page):
        return False, "The practice page's window could not be measured to place the pointer"
    if not page.is_in_front() and not page.bring_to_front():
        return False, "The practice page could not be brought to the front before the instruction"

    since = time.time()
    if not ask_lima_from_here(executor, instruction):
        message = (f"The instruction could not be sent: LIMA's {QUICK_INPUT_TITLE!r} popup did not "
                   f"open and close for the quick input hotkey")
        return False, message

    path, after = wait_for_turn_end(executor, instruction, since=since - 2.0)
    if path is None:
        message = (f"LIMA never saved a conversation for {instruction!r}, so the instruction did "
                   f"not reach the AI")
        return False, message

    passed, outcome = check(page, since)
    message = (f"{outcome} Asked: {instruction!r}. {describe_turn(after)}. "
               f"The page recorded: {page.describe_events(since)}.")
    return passed, message


def run_page_test(executor, result_name, instruction, check, focus=None, code_word=None):
    """
    Run one test on the practice page and report exactly one result.

    Args:
        result_name: the result's name in the report.
        instruction: what LIMA is asked to do, sent from the page through quick input.
        check: check(page, since) -> (passed, what happened). since is the time just before
            the instruction was sent; only events after it are this test's.
        focus: the id of the page element that starts with the keyboard focus, e.g.
            "key-box" or "first-name".
        code_word: written into the page's article (see PracticePage).
    """
    passed, message = False, "The test did not run"
    page = PracticePage(code_word=code_word)
    try:
        passed, message = _run_scenario(executor, page, instruction, check, focus)
    except PracticePageError as error:
        passed, message = False, f"The practice page could not be used: {error}"
    except Exception as error:
        passed, message = False, f"Exception during the test: {error}"
    finally:
        # No popup may be left waiting on LIMA, and the page's Edge must not outlive the test.
        try:
            cleanup()
        except Exception as error:
            print(f"  ! Cleanup of LIMA's popups failed: {error}")
        page.stop()

    executor.add_test_result(result_name, TEST_PASSED if passed else TEST_FAILED, message)
    print(("  OK " if passed else "  X ") + message)
