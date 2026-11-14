"""
Feature: Restore a maximized window.

LIMA 2.1's window_control has a restore action that returns the active window to its normal
size (tools.py, window_control). This test maximizes Notepad, hands the focus back to LIMA and
asks LIMA to switch to Notepad and restore it, then judges the result over Win32: Notepad must
be neither maximized nor minimized.

restore and maximize act on the *active* window, and while the user is typing LIMA is the
active window. The instruction therefore says "switch to" first, so the model makes Notepad
active before restoring it instead of restoring LIMA. The outcome is read from Notepad's own
window state, not from a screenshot or from LIMA's reply.
"""

from lima_test_utils import TEST_PASSED, TEST_FAILED
from feature_tests import _common

RESULT_NAME = "Feature: Restore a maximized window"

# Explicit target and both steps, so the model calls switch_to and then restore itself rather
# than asking which window to restore.
INSTRUCTION = "Switch to the Notepad window, then restore it to its normal size."

# ShowWindow is immediate; this only covers the window manager settling.
SETTLE_TIMEOUT = 10.0

# The restore happens inside the turn, but the window can settle just after the conversation
# is saved, so poll the outcome for a while afterwards.
OUTCOME_TIMEOUT = 20.0


def _run_case(executor):
    """Do the scenario; return (passed, message)."""
    if not _common.ensure_lima_ready(executor):
        return False, ("Setup: LIMA was not running with its window ready, so the test could not "
                       "run. This is not a LIMA failure.")

    hwnd = _common.open_notepad()
    if not hwnd:
        return False, ("Setup: Notepad's window did not appear, so there was no window "
                       "to maximize. This is not a LIMA failure.")

    # Maximize it and confirm it: if the window never maximized, "not maximized" at the end
    # would pass without LIMA restoring anything.
    _common.show_window(hwnd, _common.SW_MAXIMIZE)
    if not _common.wait_until(lambda: _common.is_maximized(hwnd), SETTLE_TIMEOUT):
        return False, (f"Setup: Notepad (hwnd {hwnd}) did not maximize within "
                       f"{SETTLE_TIMEOUT:.0f}s, so the test could not set up a maximized window. "
                       f"This is not a LIMA failure.")
    print("  OK Notepad is maximized")

    # send_instruction types into LIMA's chat box, so LIMA must be in front again.
    if not _common.ensure_lima_ready(executor):
        return False, ("Setup: LIMA's window was not ready after Notepad was maximized, so the "
                       "instruction was not sent. This is not a LIMA failure.")

    _common.send_instruction(INSTRUCTION)
    path, after = _common.wait_for_turn_end(executor, INSTRUCTION)

    restored = _common.wait_until(
        lambda: not _common.is_maximized(hwnd) and not _common.is_minimized(hwnd),
        OUTCOME_TIMEOUT)
    maximized = _common.is_maximized(hwnd)
    minimized = _common.is_minimized(hwnd)

    if restored:
        return True, ("LIMA switched to the maximized Notepad window and restored it: it is "
                      "neither maximized nor minimized.")

    observed = f"Notepad hwnd {hwnd}: maximized={maximized}, minimized={minimized}"
    if path is None:
        return False, (f"Instruction: LIMA never saved a conversation containing {INSTRUCTION!r}, "
                       f"so the instruction may not have reached it. After "
                       f"{OUTCOME_TIMEOUT:.0f}s, {observed}.")
    return False, (f"Outcome: after {INSTRUCTION!r} Notepad should be at its normal size "
                   f"(neither maximized nor minimized); {observed} after "
                   f"{OUTCOME_TIMEOUT:.0f}s. {_common.describe_turn(after)}")


def run(executor):
    """Run the test and report exactly one result."""
    passed, message = False, "The test did not run"
    try:
        passed, message = _run_case(executor)
    except Exception as error:
        passed, message = False, f"Exception during the test: {error}"
    finally:
        # Leave no Notepad behind for the next test, even when the scenario failed.
        _common.close_notepads()

    executor.add_test_result(RESULT_NAME, TEST_PASSED if passed else TEST_FAILED, message)
    print(("  OK " if passed else "  X ") + message)
