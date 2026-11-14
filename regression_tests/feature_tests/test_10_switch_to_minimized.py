"""
Feature: Switch to a minimized window.

LIMA 2.1's window_control switch_to brings an open window to the front and restores it first
when it is minimized (tools.py, _switch_to_window). This test minimizes Notepad behind LIMA,
asks LIMA to switch to it, and judges the result over Win32: the window must no longer be
minimized and it must own the foreground.

The instruction names the window and says "switch", because while the user types LIMA is the
active window: the model has to call switch_to rather than act on whatever is in front. The
outcome is read from Notepad's window state, never from a screenshot or from LIMA's own
window, so a reply that claims success without a switch still fails.
"""

from lima_test_utils import TEST_PASSED, TEST_FAILED
from feature_tests import _common

RESULT_NAME = "Feature: Switch to a minimized window"

# Explicit target and verb, so the model picks window_control switch_to without asking.
INSTRUCTION = "Switch to the Notepad window."

# ShowWindow on another process's window is immediate; this only covers the window manager
# settling. A failure here is the test machine, not LIMA.
SETTLE_TIMEOUT = 10.0

# The switch itself happens inside the turn, but the window can settle just after the
# conversation is saved, so poll the outcome for a while afterwards.
OUTCOME_TIMEOUT = 20.0


def _run_case(executor):
    """Do the scenario; return (passed, message)."""
    if not _common.ensure_lima_ready(executor):
        return False, ("Setup: LIMA was not running with its window ready, so the test could not "
                       "run. This is not a LIMA failure.")

    hwnd = _common.open_notepad()
    if not hwnd:
        return False, ("Setup: Notepad's window did not appear, so there was no window "
                       "to switch to. This is not a LIMA failure.")

    # Minimize it behind LIMA, then confirm it really is minimized: if the window manager
    # ignored the request, a later "not minimized" result would pass without LIMA doing
    # anything and the test would be meaningless.
    _common.show_window(hwnd, _common.SW_MINIMIZE)
    if not _common.wait_until(lambda: _common.is_minimized(hwnd), SETTLE_TIMEOUT):
        return False, (f"Setup: Notepad (hwnd {hwnd}) did not minimize within "
                       f"{SETTLE_TIMEOUT:.0f}s, so the test could not set up a minimized window. "
                       f"This is not a LIMA failure.")
    print("  OK Notepad is minimized")

    # send_instruction types into LIMA's chat box, so LIMA must be in front again.
    if not _common.ensure_lima_ready(executor):
        return False, ("Setup: LIMA's window was not ready after Notepad was minimized, so the "
                       "instruction was not sent. This is not a LIMA failure.")

    _common.send_instruction(INSTRUCTION)
    path, after = _common.wait_for_turn_end(executor, INSTRUCTION)

    switched = _common.wait_until(
        lambda: not _common.is_minimized(hwnd) and _common.foreground_root() == hwnd,
        OUTCOME_TIMEOUT)
    minimized = _common.is_minimized(hwnd)
    foreground = _common.foreground_root()

    if switched:
        return True, ("LIMA switched to the minimized Notepad window: it was restored (not "
                      "minimized) and it owns the foreground.")

    observed = (f"Notepad hwnd {hwnd}: minimized={minimized}; foreground root is hwnd "
                f"{foreground} ({'Notepad' if foreground == hwnd else 'not Notepad'})")
    if path is None:
        return False, (f"Instruction: LIMA never saved a conversation containing {INSTRUCTION!r}, "
                       f"so the instruction may not have reached it. After "
                       f"{OUTCOME_TIMEOUT:.0f}s, {observed}.")
    return False, (f"Outcome: after {INSTRUCTION!r} Notepad should be restored and in front; "
                   f"{observed} after {OUTCOME_TIMEOUT:.0f}s. {_common.describe_turn(after)}")


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
