"""
Feature: Type letters that are not on the keyboard.

LIMA 2.1.0.2 (PR #173) fixed ``type_text`` for characters the keyboard layout has no key
for: pyautogui silently dropped them, so "Xin chào thế giới" arrived as "Xin cho th gii".
``tools.py`` ``_write`` now sends any non-ASCII character as a Unicode key event
(``SendInput`` with ``KEYEVENTF_UNICODE``) instead of pyautogui.

This test opens an empty Notepad, puts LIMA back in front, and asks LIMA to switch to
Notepad and type that sentence. The pass condition is the text in Notepad's own text area
(read over UI Automation), NFC-normalised on both sides, so a dropped or mangled letter
fails the test. On failure the exact text Notepad holds is quoted with repr, which makes
the mangled character visible.
"""

import unicodedata

from lima_test_utils import TEST_PASSED, TEST_FAILED
from feature_tests import _common

RESULT_NAME = "Feature: Type letters not on the keyboard"

TARGET_TEXT = "Xin chào thế giới"

# Saying "without pressing Enter" picks type_text on v2.1.0.5, where type_text_and_enter
# still exists, and keeps type_text's default press_enter=False on newer builds where the
# two were merged.
INSTRUCTION = ("Switch to the Notepad window, then type this text into it without pressing "
               "Enter: " + TARGET_TEXT)

# Typing is done before the turn is saved, so this only covers the last keystrokes landing
# and Notepad's text being readable over UI Automation.
TEXT_TIMEOUT = 30.0


def _normalise(text):
    """NFC, so a combining accent and a precomposed letter compare equal."""
    return unicodedata.normalize("NFC", text or "")


def _notepad_holds(hwnd, wanted):
    return wanted in _normalise(_common.notepad_text(hwnd))


def _run_case(executor, state):
    """Do the scenario; return (passed, message). state['hwnd'] is closed in cleanup."""
    if not _common.ensure_lima_ready(executor):
        return False, "LIMA was not running with its window ready, so the test could not run"

    # open_notepad closes any Notepad left over from an earlier test, so the window found is
    # the empty one this test types into.
    hwnd = _common.open_notepad()
    state["hwnd"] = hwnd
    if not hwnd:
        return False, ("Notepad's window did not appear, so there was nothing for LIMA to "
                       "type into")

    # send_instruction types into LIMA's chat box, so LIMA must be in front; the model then
    # switches to Notepad itself, which also exercises window switching.
    if not _common.ensure_lima_ready(executor):
        return False, "LIMA could not be focused before sending the instruction"

    _common.send_instruction(INSTRUCTION)
    _conversation, after = _common.wait_for_turn_end(executor, INSTRUCTION)

    wanted = _normalise(TARGET_TEXT)
    if _common.wait_until(lambda: _notepad_holds(hwnd, wanted), TEXT_TIMEOUT):
        return True, (
            f"Notepad holds the expected text after LIMA typed it: "
            f"{_common.notepad_text(hwnd)!r}. Non-keyboard letters such as ế and ớ arrived "
            f"intact. {_common.describe_turn(after)}")

    actual = _common.notepad_text(hwnd)
    if actual is None:
        seen = "Notepad's text could not be read over UI Automation"
    else:
        seen = f"Notepad holds {actual!r}"
    return False, (
        f"Expected Notepad to hold {TARGET_TEXT!r} (NFC) after LIMA typed it, but {seen}. "
        f"{_common.describe_turn(after)}")


def run(executor):
    """Run the test and report exactly one result."""
    passed, message = False, "The test did not run"
    state = {"hwnd": 0}
    try:
        passed, message = _run_case(executor, state)
    except Exception as error:
        passed, message = False, f"Exception during the test: {error}"
    finally:
        # Windows 11 Notepad restores unsaved tabs, so empty the document before closing it;
        # otherwise this test's typing reappears in the next test's Notepad.
        if state["hwnd"]:
            try:
                _common.clear_notepad(state["hwnd"])
            except Exception as error:
                print(f"  ! Could not clear Notepad during cleanup: {error}")
        try:
            _common.close_notepads()
        except Exception as error:
            print(f"  ! Could not close Notepad during cleanup: {error}")

    executor.add_test_result(RESULT_NAME, TEST_PASSED if passed else TEST_FAILED, message)
    print(("  OK " if passed else "  X ") + message)
